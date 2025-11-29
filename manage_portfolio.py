from models.database import get_db, User, UserHolding

def add_stock(symbol, quantity, avg_cost):
    """Add a single stock to portfolio"""
    db = next(get_db())
    user = db.query(User).first()
    
    if not user:
        print("❌ No user found! Run 'python main.py setup' first.")
        db.close()
        return
    
    # Check if already exists
    existing = db.query(UserHolding).filter(
        UserHolding.user_id == user.id,
        UserHolding.symbol == symbol
    ).first()
    
    if existing:
        # Update existing
        old_qty = float(existing.quantity)
        old_cost = float(existing.avg_cost)
        existing.quantity = quantity
        existing.avg_cost = avg_cost
        print(f"✅ Updated {symbol}:")
        print(f"   Old: {old_qty} shares @ ${old_cost:.2f}")
        print(f"   New: {quantity} shares @ ${avg_cost:.2f}")
    else:
        # Add new
        holding = UserHolding(
            user_id=user.id,
            symbol=symbol,
            quantity=quantity,
            avg_cost=avg_cost,
            asset_type="stock"
        )
        db.add(holding)
        print(f"✅ Added {symbol}: {quantity} shares @ ${avg_cost:.2f}")
    
    db.commit()
    db.close()

def remove_stock(symbol):
    """Remove a stock from portfolio"""
    db = next(get_db())
    user = db.query(User).first()
    
    deleted = db.query(UserHolding).filter(
        UserHolding.user_id == user.id,
        UserHolding.symbol == symbol
    ).delete()
    
    db.commit()
    db.close()
    
    if deleted:
        print(f"✅ Removed {symbol} from portfolio")
    else:
        print(f"❌ {symbol} not found in portfolio")

def view_portfolio():
    """View current portfolio"""
    db = next(get_db())
    user = db.query(User).first()
    
    if not user:
        print("❌ No user found!")
        db.close()
        return
    
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    
    print("\n" + "="*70)
    print("📊 CURRENT PORTFOLIO")
    print("="*70)
    print(f"User: {user.name or user.email}")
    print(f"Email: {user.email}")
    print("-"*70)
    
    if not holdings:
        print("❌ Portfolio is empty! Add stocks with:")
        print("   python manage_portfolio.py add SYMBOL QUANTITY PRICE")
    else:
        print(f"{'Symbol':<10} {'Quantity':>12} {'Avg Cost':>15} {'Total Value':>18}")
        print("-"*70)
        
        total_value = 0
        for h in holdings:
            qty = float(h.quantity)
            cost = float(h.avg_cost)
            value = qty * cost
            total_value += value
            print(f"{h.symbol:<10} {qty:>12.2f} ${cost:>14.2f} ${value:>17.2f}")
        
        print("-"*70)
        print(f"{'TOTAL':>37} ${total_value:>17.2f}")
        print("-"*70)
        print(f"\nTotal Holdings: {len(holdings)} stocks")
    
    print("="*70 + "\n")
    db.close()

def list_stocks():
    """Quick list of stock symbols only"""
    db = next(get_db())
    user = db.query(User).first()
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    
    if holdings:
        symbols = [h.symbol for h in holdings]
        print(f"\n📊 Monitoring: {', '.join(symbols)}\n")
    else:
        print("\n❌ No stocks in portfolio\n")
    
    db.close()

def show_help():
    """Show usage instructions"""
    print("\n" + "="*70)
    print("📊 PORTFOLIO MANAGEMENT TOOL")
    print("="*70)
    print("\nUSAGE:")
    print("  python manage_portfolio.py view")
    print("  python manage_portfolio.py list")
    print("  python manage_portfolio.py add SYMBOL QUANTITY PRICE")
    print("  python manage_portfolio.py remove SYMBOL")
    print("\nEXAMPLES:")
    print("  python manage_portfolio.py view")
    print("  python manage_portfolio.py list")
    print("  python manage_portfolio.py add AAPL 100 175.50")
    print("  python manage_portfolio.py add MSFT 50 380.00")
    print("  python manage_portfolio.py remove TSLA")
    print("\nNOTES:")
    print("  - If a stock already exists, 'add' will UPDATE it")
    print("  - Changes take effect on next monitoring cycle")
    print("  - Use 'view' to see your current portfolio")
    print("="*70 + "\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "view":
        view_portfolio()
    
    elif command == "list":
        list_stocks()
    
    elif command == "add":
        if len(sys.argv) != 5:
            print("❌ Error: 'add' requires 3 arguments")
            print("Usage: python manage_portfolio.py add SYMBOL QUANTITY PRICE")
            print("Example: python manage_portfolio.py add AAPL 100 175.50")
            sys.exit(1)
        
        symbol = sys.argv[2].upper()
        try:
            quantity = float(sys.argv[3])
            price = float(sys.argv[4])
            add_stock(symbol, quantity, price)
        except ValueError:
            print("❌ Error: QUANTITY and PRICE must be numbers")
            sys.exit(1)
    
    elif command == "remove":
        if len(sys.argv) != 3:
            print("❌ Error: 'remove' requires 1 argument")
            print("Usage: python manage_portfolio.py remove SYMBOL")
            print("Example: python manage_portfolio.py remove TSLA")
            sys.exit(1)
        
        symbol = sys.argv[2].upper()
        remove_stock(symbol)
    
    elif command == "help":
        show_help()
    
    else:
        print(f"❌ Unknown command: {command}")
        show_help()
        sys.exit(1)