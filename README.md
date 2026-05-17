# west-java-waste-dss
Python-based Decision Support System for prioritizing municipal waste management in West Java using the SAW method.
# Python-Based DSS for Waste Management Prioritization in West Java

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.20%2B-red)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

## Overview
This repository contains the reproducibility package and source code for the **Decision Support System (DSS)** developed to prioritize municipal waste management areas in West Java. 

The system implements the **Simple Additive Weighting (SAW)** method to evaluate 27 regencies and cities based on multi-criteria indicators derived from the SIPSN (National Waste Management Information System) database. It is designed to assist policymakers in allocating limited infrastructure and management resources transparently and objectively.

## Features
* **Multi-Criteria Decision-Making (MCDM):** Implements the SAW algorithm, classifying alternatives into High, Medium, and Low priorities.
* **Interactive Weight Adjustment:** Users can dynamically adjust the weights for Waste Generation, Unmanaged Waste, Managed Waste, and Landfill Score to perform real-time sensitivity analysis.
* **Geospatial Visualization:** Features an interactive PyDeck map that dynamically centers and visualizes priority areas using color-coded nodes and SAW-scaled radii.
* **Automated Recommendations:** Generates actionable policy recommendations based on statistical quartiles (e.g., identifying open dumping practices or critical waste generation levels).
* **Exportable Results:** Full DSS ranking tables can be downloaded directly as CSV files for reporting.

## Repository Structure
* `app_final.py`: The main Streamlit application script containing the SAW logic and dashboard UI.
* `Jawa_Barat_Waste_2024_2025_Capaian_Gabungan.csv`: The raw input dataset containing SIPSN waste metrics.
* `West_Java_Coordinates.csv`: Geospatial coordinate mapping for all 27 West Java municipalities.
* `requirements.txt`: List of Python dependencies required to run the dashboard.

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/maulida-butar/west-java-waste-dss.git](https://github.com/maulida-butar/west-java-waste-dss.git)
   cd west-java-waste-dss
