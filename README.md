# Robot Selection Decision Support System (Robot DSS)

A machine thinking decision-support system for industrial robot selection.

The system represents robot specifications and application requirements in a **Neo4j knowledge graph** and evaluates candidate robots using **parameterised Cypher queries** that perform constraint checking, suitability scoring, overspecification penalties, and uncertainty handling.

A **Streamlit interface** allows users to interactively explore robot recommendations and adjust decision priorities through weighting.

---

## Features

- Graph-based knowledge representation (Neo4j)
- Constraint-based robot filtering
- Multi-criteria suitability scoring
- Overspecification penalty handling
- Uncertainty-aware reasoning (e.g. cleanroom capability)
- Interactive decision interface (Streamlit)

---

## Project Structure

```
Robot_DSS_app/

├── app.py                # Streamlit application
├── db.py                 # Neo4j database connection
├── charts.py             # Visualisation functions
├── components.py         # UI components
├── utils_format.py       # Formatting utilities

├── testing_scripts/      # Query testing and development scripts
├── app_version_histories/

├── data/                 # Robot and application datasets
└── README.md
```

---

## Requirements

- Python 3.10+
- Neo4j database (local or remote)

Python packages:

- streamlit
- neo4j
- pandas
- numpy
- plotly

---

## Installation

Clone the repository:

```
git clone https://github.com/32rejbf32098bc/Robot_DSS_app.git
cd Robot_DSS_app
```

Create a virtual environment (recommended):

```
python -m venv .venv
```

Activate the virtual environment:

Windows

```
.venv\Scripts\activate
```

Mac / Linux

```
source .venv/bin/activate
```

Install dependencies:

```
pip install -r requirements.txt
```

---

## Configure Neo4j

Start your Neo4j database and update the `.env` file with your credentials:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=yourpassword
```

Ensure the robot and application datasets are loaded into the database before running the application.

---

## Running the Application

Launch the Streamlit interface:

```
streamlit run app.py
```

The application will open in your browser at:

```
http://localhost:8501
```

---

## Example Workflow

1. Select an application scenario.
2. Adjust the decision criteria weights.
3. View ranked robot recommendations.
4. Inspect explanation outputs including constraint violations, overspecification penalties, and uncertainty flags.

---

## Repository Purpose

This repository contains the implementation used in the **MENGM0059 Machine Thinking in Smart Manufacturing** project report.

The system demonstrates how graph-based reasoning can support structured engineering decision-making in robot selection.

---

## Author

Luis Nunes  
University of Bristol  
MEng Mechanical Engineering
