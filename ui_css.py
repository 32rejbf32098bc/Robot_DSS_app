# ui_css.py
import streamlit as st

def inject_css():
    st.markdown("""
    <style>

/* SUMMARY METRIC LABEL (title) */
div[data-testid="stMetricLabel"] {
    font-size: 12px !important;
    font-weight: 500 !important;
}

/* SUMMARY METRIC VALUE (number) */
div[data-testid="stMetricValue"] {
    font-size: 20px !important;
    font-weight: 700 !important;
}

/* Optional: reduce vertical spacing */
div[data-testid="stMetric"] {
    padding-top: 2px;
    padding-bottom: 2px;
}

    </style>
    """, unsafe_allow_html=True)