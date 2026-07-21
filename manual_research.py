"""Structured manual-research inputs for forecasts without clean public APIs.

Enter only sourced findings. Empty lists mean no research has been recorded;
they are intentional and must not be interpreted as zero events or a NO signal.
Dates should use ISO ``YYYY-MM-DD`` format and URLs should point to the primary
source whenever possible.
"""


MANUAL_RESEARCH = {
    2: {
        "forecast": "Critical mineral strategic reserve",
        "status": "manual research required",
        "entry_fields": [
            "source_url",
            "publication_date",
            "government_body",
            "mineral",
            "action_type",
            "allocated_funding_usd",
            "qualifies_under_resolution_criteria",
            "notes",
        ],
        "entries": [],
    },
    3: {
        "forecast": "Data center capacity gap",
        "status": "manual research required",
        "entry_fields": [
            "source_url",
            "source_name",
            "publication_date",
            "measurement_period",
            "geography",
            "reported_capacity_gap_pct",
            "gap_definition",
            "notes",
        ],
        "entries": [],
    },
    7: {
        "forecast": "Non-US/China sovereign AI buildout",
        "status": "manual research required",
        "entry_fields": [
            "source_url",
            "announcement_date",
            "government",
            "program_name",
            "public_funding_local_currency",
            "currency",
            "public_funding_usd_at_announcement",
            "funding_status",
            "qualifies_under_resolution_criteria",
            "notes",
        ],
        "entries": [],
    },
    8: {
        "forecast": "National champion equity stake",
        "status": "manual research required",
        "entry_fields": [
            "source_url",
            "action_date",
            "government",
            "company",
            "action_type",
            "equity_stake_pct",
            "designation_language",
            "qualifies_under_resolution_criteria",
            "notes",
        ],
        "entries": [],
    },
    10: {
        "forecast": "Nuclear/SMR permitting fast-track",
        "status": "manual research required",
        "entry_fields": [
            "source_url",
            "action_date",
            "agency",
            "pathway_name",
            "formal_action_type",
            "effective_date",
            "data_center_connection",
            "qualifies_under_resolution_criteria",
            "notes",
        ],
        "entries": [],
    },
}
