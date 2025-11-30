#!/usr/bin/env python3
"""
Portfolio News Alert - Web Interface
Streamlit Dashboard pour gérer votre portfolio et voir les alertes
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import plotly.express as px
import plotly.graph_objects as go

from models.database import (
    init_db, get_db, User, UserHolding, NewsArticle, 
    NewsAnalysis, Notification
)
from services.fmp_client import FMPClient
from services.ai_analyzer import AIAnalyzer
from main import PortfolioNewsMonitor

# Configuration de la page
st.set_page_config(
    page_title="Portfolio News Alert",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Style CSS personnalisé
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 1rem;
    }
    .alert-urgent {
        border-left: 5px solid #e74c3c;
        padding: 1rem;
        background: #fee;
        margin: 0.5rem 0;
    }
    .alert-normal {
        border-left: 5px solid #3498db;
        padding: 1rem;
        background: #f0f8ff;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialiser la base de données
init_db()

# Services
@st.cache_resource
def get_services():
    return {
        'fmp': FMPClient(),
        'ai': AIAnalyzer(),
        'monitor': PortfolioNewsMonitor()
    }

services = get_services()

# Session state pour l'utilisateur
if 'user_email' not in st.session_state:
    st.session_state.user_email = 'demo@example.com'

# Sidebar - Navigation
with st.sidebar:
    st.image("https://via.placeholder.com/150x50/2c3e50/ffffff?text=Portfolio+Alert", use_container_width=True)
    st.markdown("---")
    
    page = st.radio(
        "Navigation",
        ["🏠 Dashboard", "📊 Portfolio", "🔔 Alertes", "⚙️ Configuration", "▶️ Lancer Scan"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 👤 Utilisateur")
    st.info(f"**{st.session_state.user_email}**")
    
    st.markdown("---")
    st.markdown("### 📈 Stats Rapides")
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if user:
        holdings_count = db.query(UserHolding).filter(UserHolding.user_id == user.id).count()
        alerts_count = db.query(Notification).filter(Notification.user_id == user.id).count()
        
        st.metric("Actions suivies", holdings_count)
        st.metric("Alertes reçues", alerts_count)
    
    db.close()

# ===========================
# PAGE 1 : DASHBOARD
# ===========================
if page == "🏠 Dashboard":
    st.markdown('<p class="main-header">📊 Dashboard</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("Utilisateur non trouvé. Exécutez `python main.py setup` pour créer l'utilisateur demo.")
        db.close()
        st.stop()
    
    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)
    
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    recent_alerts = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.sent_at.desc()).limit(7).all()
    
    high_impact_alerts = db.query(Notification).join(NewsArticle).join(NewsAnalysis).filter(
        Notification.user_id == user.id,
        NewsAnalysis.impact_score >= 7
    ).count()
    
    with col1:
        st.metric("📌 Actions Suivies", len(holdings))
    
    with col2:
        st.metric("🔔 Alertes (7j)", len(recent_alerts))
    
    with col3:
        st.metric("⚠️ Impact Élevé", high_impact_alerts)
    
    with col4:
        active_status = "✅ Actif" if user.active else "❌ Inactif"
        st.metric("État", active_status)
    
    st.markdown("---")
    
    # Graphique : Portfolio Value (simulé)
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📈 Valeur du Portfolio (Simulée)")
        
        if holdings:
            portfolio_data = []
            for holding in holdings:
                try:
                    quote = services['fmp'].get_stock_quote(holding.symbol)
                    current_price = quote.get('price', 0)
                    value = current_price * float(holding.quantity)
                    cost = float(holding.avg_cost) * float(holding.quantity)
                    pnl = value - cost
                    pnl_pct = (pnl / cost * 100) if cost > 0 else 0
                    
                    portfolio_data.append({
                        'Symbol': holding.symbol,
                        'Quantité': holding.quantity,
                        'Prix Actuel': current_price,
                        'Valeur': value,
                        'Coût': cost,
                        'P&L': pnl,
                        'P&L %': pnl_pct
                    })
                except:
                    pass
            
            if portfolio_data:
                df = pd.DataFrame(portfolio_data)
                
                # Pie chart de la répartition
                fig = px.pie(df, values='Valeur', names='Symbol', 
                            title='Répartition du Portfolio',
                            color_discrete_sequence=px.colors.qualitative.Set3)
                st.plotly_chart(fig, use_container_width=True)
                
                # Tableau détaillé
                st.dataframe(
                    df.style.format({
                        'Prix Actuel': '${:.2f}',
                        'Valeur': '${:.2f}',
                        'Coût': '${:.2f}',
                        'P&L': '${:.2f}',
                        'P&L %': '{:.2f}%'
                    }),
                    use_container_width=True
                )
        else:
            st.info("Aucune action dans votre portfolio. Allez dans 📊 Portfolio pour en ajouter.")
    
    with col2:
        st.subheader("🔥 Alertes Récentes")
        
        if recent_alerts:
            for notif in recent_alerts[:5]:
                article = db.query(NewsArticle).filter(NewsArticle.id == notif.article_id).first()
                analysis = db.query(NewsAnalysis).filter(NewsAnalysis.article_id == notif.article_id).first()
                
                if article and analysis:
                    impact_emoji = "🔴" if analysis.impact_score >= 7 else "🟡" if analysis.impact_score >= 5 else "🟢"
                    
                    with st.expander(f"{impact_emoji} {article.symbol} - {analysis.summary[:50]}..."):
                        st.write(f"**Impact:** {analysis.impact_score}/10")
                        st.write(f"**Sentiment:** {analysis.sentiment}")
                        st.write(f"**Urgence:** {analysis.urgency}")
                        st.write(f"**Date:** {article.published_date.strftime('%Y-%m-%d %H:%M')}")
                        st.write(f"**Source:** {article.source}")
                        st.markdown(f"[Lire l'article]({article.url})")
        else:
            st.info("Aucune alerte récente.")
    
    # Graphique : Impact Score Distribution
    st.markdown("---")
    st.subheader("📊 Distribution des Scores d'Impact (30 derniers jours)")
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    analyses = db.query(NewsAnalysis).join(NewsArticle).join(Notification).filter(
        Notification.user_id == user.id,
        NewsArticle.published_date >= thirty_days_ago
    ).all()
    
    if analyses:
        impact_scores = [a.impact_score for a in analyses]
        
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=impact_scores,
            nbinsx=10,
            marker_color='#3498db',
            name='Impact Score'
        ))
        fig.update_layout(
            title='Répartition des Scores d\'Impact',
            xaxis_title='Score',
            yaxis_title='Nombre d\'alertes',
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    db.close()

# ===========================
# PAGE 2 : PORTFOLIO
# ===========================
elif page == "📊 Portfolio":
    st.markdown('<p class="main-header">📊 Gérer mon Portfolio</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("Utilisateur non trouvé.")
        db.close()
        st.stop()
    
    # Afficher le portfolio actuel
    st.subheader("🔹 Actions Actuelles")
    
    holdings = db.query(UserHolding).filter(UserHolding.user_id == user.id).all()
    
    if holdings:
        holdings_data = []
        for h in holdings:
            holdings_data.append({
                'ID': h.id,
                'Symbole': h.symbol,
                'Quantité': h.quantity,
                'Prix Moyen': f"${h.avg_cost:.2f}",
                'Type': h.asset_type
            })
        
        df = pd.DataFrame(holdings_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Supprimer une action
        st.markdown("---")
        st.subheader("🗑️ Supprimer une Action")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            holding_to_delete = st.selectbox(
                "Sélectionner l'action à supprimer",
                options=[f"{h.symbol} ({h.quantity} actions)" for h in holdings],
                key="delete_holding"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("🗑️ Supprimer", type="secondary"):
                symbol = holding_to_delete.split(" ")[0]
                holding = db.query(UserHolding).filter(
                    UserHolding.user_id == user.id,
                    UserHolding.symbol == symbol
                ).first()
                
                if holding:
                    db.delete(holding)
                    db.commit()
                    st.success(f"✅ {symbol} supprimé avec succès !")
                    st.rerun()
    else:
        st.info("Votre portfolio est vide. Ajoutez des actions ci-dessous.")
    
    # Ajouter une nouvelle action
    st.markdown("---")
    st.subheader("➕ Ajouter une Action")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        new_symbol = st.text_input("Symbole (ex: AAPL)", key="new_symbol").upper()
    
    with col2:
        new_quantity = st.number_input("Quantité", min_value=0.01, value=1.0, step=0.01, key="new_quantity")
    
    with col3:
        new_avg_cost = st.number_input("Prix Moyen ($)", min_value=0.01, value=100.0, step=0.01, key="new_avg_cost")
    
    if st.button("➕ Ajouter au Portfolio", type="primary"):
        if new_symbol:
            # Vérifier si déjà existant
            existing = db.query(UserHolding).filter(
                UserHolding.user_id == user.id,
                UserHolding.symbol == new_symbol
            ).first()
            
            if existing:
                st.warning(f"⚠️ {new_symbol} existe déjà dans votre portfolio.")
            else:
                new_holding = UserHolding(
                    user_id=user.id,
                    symbol=new_symbol,
                    quantity=new_quantity,
                    avg_cost=new_avg_cost,
                    asset_type='stock'
                )
                db.add(new_holding)
                db.commit()
                st.success(f"✅ {new_symbol} ajouté avec succès !")
                st.rerun()
        else:
            st.error("❌ Veuillez entrer un symbole valide.")
    
    db.close()

# ===========================
# PAGE 3 : ALERTES
# ===========================
elif page == "🔔 Alertes":
    st.markdown('<p class="main-header">🔔 Historique des Alertes</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("Utilisateur non trouvé.")
        db.close()
        st.stop()
    
    # Filtres
    col1, col2, col3 = st.columns(3)
    
    with col1:
        days_filter = st.selectbox("Période", [7, 14, 30, 90, 365], index=2)
    
    with col2:
        impact_filter = st.slider("Impact minimum", 0, 10, 5)
    
    with col3:
        category_filter = st.multiselect(
            "Catégorie",
            ["Earnings", "Management", "Regulatory", "Product", "Market", "Legal", "M&A", "Financial", "Other"],
            default=[]
        )
    
    # Récupérer les alertes
    cutoff_date = datetime.utcnow() - timedelta(days=days_filter)
    
    query = db.query(Notification).join(NewsArticle).join(NewsAnalysis).filter(
        Notification.user_id == user.id,
        NewsArticle.published_date >= cutoff_date,
        NewsAnalysis.impact_score >= impact_filter
    )
    
    if category_filter:
        query = query.filter(NewsAnalysis.category.in_(category_filter))
    
    notifications = query.order_by(NewsArticle.published_date.desc()).all()
    
    st.write(f"**{len(notifications)} alertes trouvées**")
    
    if notifications:
        for notif in notifications:
            article = db.query(NewsArticle).filter(NewsArticle.id == notif.article_id).first()
            analysis = db.query(NewsAnalysis).filter(NewsAnalysis.article_id == notif.article_id).first()
            
            if article and analysis:
                # Styling selon urgence
                is_urgent = analysis.urgency in ['Immediate', 'Hours']
                alert_class = "alert-urgent" if is_urgent else "alert-normal"
                
                st.markdown(f'<div class="{alert_class}">', unsafe_allow_html=True)
                
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.markdown(f"### {article.symbol}: {article.title}")
                    st.write(f"**📰 {analysis.summary}**")
                    st.write(f"**Source:** {article.source} | **Publié:** {article.published_date.strftime('%Y-%m-%d %H:%M')}")
                
                with col2:
                    impact_color = "🔴" if analysis.impact_score >= 7 else "🟡" if analysis.impact_score >= 5 else "🟢"
                    st.metric("Impact", f"{impact_color} {analysis.impact_score}/10")
                    st.write(f"**Urgence:** {analysis.urgency}")
                    st.write(f"**Catégorie:** {analysis.category}")
                
                if st.button(f"Lire l'article", key=f"read_{article.id}"):
                    st.markdown(f"[Ouvrir dans un nouvel onglet]({article.url})")
                
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown("---")
    else:
        st.info("Aucune alerte trouvée avec ces critères.")
    
    db.close()

# ===========================
# PAGE 4 : CONFIGURATION
# ===========================
elif page == "⚙️ Configuration":
    st.markdown('<p class="main-header">⚙️ Configuration</p>', unsafe_allow_html=True)
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if not user:
        st.error("Utilisateur non trouvé.")
        db.close()
        st.stop()
    
    st.subheader("👤 Informations Utilisateur")
    
    col1, col2 = st.columns(2)
    
    with col1:
        new_name = st.text_input("Nom", value=user.name or "")
        new_email = st.text_input("Email", value=user.email)
    
    with col2:
        user_active = st.checkbox("Compte actif", value=user.active)
    
    if st.button("💾 Sauvegarder", type="primary"):
        user.name = new_name
        user.email = new_email
        user.active = user_active
        db.commit()
        st.success("✅ Paramètres sauvegardés !")
        st.session_state.user_email = new_email
        st.rerun()
    
    st.markdown("---")
    st.subheader("🔔 Préférences de Notification")
    
    st.info("💡 Les paramètres avancés (seuil d'impact, fréquence) sont dans `config/settings.py`")
    
    with st.expander("📋 Voir les paramètres actuels"):
        from config.settings import settings
        
        st.write(f"**Intervalle de polling:** {settings.polling_interval_minutes} minutes")
        st.write(f"**Seuil d'impact:** {settings.impact_threshold}/10")
        st.write(f"**Lookback des news:** {settings.news_lookback_hours} heures")
        st.write(f"**SMTP Host:** {settings.smtp_host}")
    
    st.markdown("---")
    st.subheader("🗑️ Zone Dangereuse")
    
    if st.button("🗑️ Supprimer toutes mes alertes", type="secondary"):
        notifications = db.query(Notification).filter(Notification.user_id == user.id).all()
        for n in notifications:
            db.delete(n)
        db.commit()
        st.warning("⚠️ Toutes vos alertes ont été supprimées.")
    
    db.close()

# ===========================
# PAGE 5 : LANCER SCAN
# ===========================
elif page == "▶️ Lancer Scan":
    st.markdown('<p class="main-header">▶️ Lancer un Scan Manuel</p>', unsafe_allow_html=True)
    
    st.info("🔍 Cliquez sur le bouton ci-dessous pour lancer un cycle de monitoring immédiatement.")
    
    if st.button("🚀 Lancer le Scan", type="primary"):
        with st.spinner("Analyse en cours... Cela peut prendre 30-60 secondes."):
            try:
                services['monitor'].run_monitoring_cycle()
                st.success("✅ Scan terminé avec succès ! Vérifiez vos emails et l'onglet 🔔 Alertes.")
            except Exception as e:
                st.error(f"❌ Erreur pendant le scan : {e}")
    
    st.markdown("---")
    st.subheader("📊 Dernière Exécution")
    
    db = next(get_db())
    user = db.query(User).filter(User.email == st.session_state.user_email).first()
    
    if user:
        last_notif = db.query(Notification).filter(
            Notification.user_id == user.id
        ).order_by(Notification.sent_at.desc()).first()
        
        if last_notif:
            st.write(f"**Date:** {last_notif.sent_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.write("Aucune exécution enregistrée.")
    
    db.close()

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #7f8c8d;'>
        Portfolio News Alert v1.0 | Powered by Claude AI & FMP
    </div>
    """,
    unsafe_allow_html=True
)