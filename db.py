# db.py
from __future__ import annotations

from typing import Dict, Any, List, Optional
import pandas as pd
import streamlit as st
from neo4j import GraphDatabase


def run_query(driver, query: str, params: Dict[str, Any] | None = None, database: str | None = None) -> pd.DataFrame:
    with driver.session(database=database) as session:
        result = session.run(query, params or {})
        rows: List[Dict[str, Any]] = [r.data() for r in result]
    return pd.DataFrame(rows)


def ensure_driver(
    current_driver,
    uri: str,
    user: str,
    password: str,
    database: str,
    conn_error_key: str = "conn_error",
    driver_key: str = "driver",
):
    """
    Connect once and store in st.session_state[driver_key].
    """
    if current_driver is not None:
        return current_driver

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        _ = run_query(driver, "RETURN 1 AS ok;", database=database)
        st.session_state[conn_error_key] = None
        st.session_state[driver_key] = driver
        return driver
    except Exception as e:
        st.session_state[driver_key] = None
        st.session_state[conn_error_key] = str(e)
        return None