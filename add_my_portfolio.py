from models.database import get_db, User, UserHolding

def add_my_portfolio():
    db = next(get_db())
    
    # Update the demo user email to YOUR email
    user = db.query(User).filter(User.email == "demo@example.com").first()
    user.email = "YOUR_REAL_EMAIL@gmail.com"  # Change this!
    user.name = "Your Name"  # Change this!
    
    # Delete demo holdings
    db.query(UserHolding).filter(UserHolding.user_id == user.id).delete()
    
    # Add YOUR holdings
    my_holdings = [
        # Format: (symbol, quantity, average_cost, asset_type)
        ("AAPL", 10, 150.00, "stock"),
        ("TSLA", 5, 200.00, "stock"),
        ("LLY", 3, 780, "stock"),
        ("WMT", 6, 98, "stock"),
        ("NVDA", 8, 136, "stock")
        # Add more of your stocks here...
    ]
    
    for symbol, qty, cost, asset_type in my_holdings:
        holding = UserHolding(
            user_id=user.id,
            symbol=symbol,
            quantity=qty,
            avg_cost=cost,
            asset_type=asset_type
        )
        db.add(holding)
    
    db.commit()
    print(f"✅ Portfolio updated for {user.email}")
    print(f"   Monitoring {len(my_holdings)} stocks")

if __name__ == "__main__":
    add_my_portfolio()