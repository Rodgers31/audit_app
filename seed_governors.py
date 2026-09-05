#!/usr/bin/env python3
"""Patch existing county entities in the DB with governor names from enhanced_county_data.json.

Usage:  cd audit_app/backend && ../venv/bin/python ../seed_governors.py
"""
import json
import os
import sys

# Run from backend/ so load_dotenv() finds .env
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv

load_dotenv()  # explicitly load backend/.env

from database import engine
from sqlalchemy import text
from sqlalchemy.orm import Session

# Load governor data from JSON
json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "data", "reference", "enhanced_county_data.json")
with open(json_path) as f:
    county_data = json.load(f)["county_data"]

# Build lookup: "Kwale County" -> governor, "Kwale" -> governor
gov_lookup = {}
for county_name, info in county_data.items():
    gov = info.get("governor", "")
    if gov:
        gov_lookup[county_name.lower()] = gov
        gov_lookup[f"{county_name} county".lower()] = gov

updated = 0

with Session(engine) as session:
    rows = session.execute(
        text("SELECT id, canonical_name, metadata FROM entities WHERE type = 'COUNTY'")
    ).fetchall()

    print(f"Found {len(rows)} county entities in DB")

    for row in rows:
        entity_id, canonical_name, metadata = row
        if metadata is None:
            metadata = {}

        gov = gov_lookup.get(canonical_name.lower())
        if gov and metadata.get("governor") != gov:
            metadata["governor"] = gov
            session.execute(
                text("UPDATE entities SET metadata = CAST(:meta AS jsonb) WHERE id = :id"),
                {"meta": json.dumps(metadata), "id": entity_id},
            )
            updated += 1
            print(f"  ✓ {canonical_name}: {gov}")
        elif gov:
            print(f"  = {canonical_name}: already has {gov}")
        else:
            print(f"  ? {canonical_name}: no governor data found")

    session.commit()

print(f"\nDone — updated {updated} county entities with governor names")
    session.commit()

print(f"\nDone — updated {updated} county entities with governor names")
