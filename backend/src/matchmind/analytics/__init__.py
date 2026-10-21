"""Lakehouse export of the synthetic match data: star-schema tables for Microsoft
Fabric (Parquet, with a CSV fallback), plus a labelled decision dataset for ML.

Every number is computed by the stats engine (`matchmind.stats`) and the rule-based
Spotter; nothing here estimates or models a value of its own.
"""
