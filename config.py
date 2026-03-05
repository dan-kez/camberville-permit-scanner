"""Constants for permit scanner."""

from datetime import datetime, timedelta

# Target squares: name → (lat, lng)
SQUARES = {
    "Davis": (42.3967, -71.1225),
    "Porter": (42.3884, -71.1191),
    "Central": (42.3653, -71.1037),
    "Inman": (42.3737, -71.0993),
    "Union": (42.3796, -71.0932),
}

# API endpoints
CAMBRIDGE_ALTERATION = "https://data.cambridgema.gov/resource/qu2z-8suj.json"
CAMBRIDGE_NEW_CONSTRUCTION = "https://data.cambridgema.gov/resource/9qm7-wbdc.json"
SOMERVILLE_PERMITS = "https://data.somervillema.gov/resource/nneb-s3f7.json"

# Property database endpoints
CAMBRIDGE_PROPERTY_DB = "https://data.cambridgema.gov/resource/waa7-ibdu.json"
SOMERVILLE_PROPERTY_DB = "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/L3_TAXPAR_POLY_ASSESS_gdb/FeatureServer/0/query"
SOMERVILLE_TOWN_ID = 274

# Defaults
DEFAULT_RADIUS_MI = 0.75
LOOKBACK_DAYS = 180
MIN_COST_THRESHOLD = 25000  # Cambridge only
DEFAULT_MIN_SCORE = 1
FETCH_LIMIT = 5000

# Lookback date as ISO string
LOOKBACK_DATE = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00")

# Keywords indicating significant renovation work
SIGNIFICANT_KEYWORDS = [
    "gut", "renovate", "renovation", "remodel", "remodeling",
    "addition", "demolition", "demolish", "new construction",
    "convert", "conversion", "rebuild", "reconfigure",
    "structural", "foundation", "framing", "extensive",
    "full", "complete", "major", "total",
]

# Keywords indicating minor/routine work (exclude)
MINOR_KEYWORDS = [
    "smoke detector", "carbon monoxide", "co detector",
    "furnace", "boiler", "water heater", "hot water",
    "sign", "signage", "banner",
    "temporary", "temp ",
    "fire alarm", "sprinkler",
    "certificate of occupancy", "cert of occ",
    "solar", "panel",
    "insulation", "weatherization",
    "fence", "shed",
    "re-roof", "reroof", "roofing",
    "window replacement", "replace windows",
    "siding",
]

# Statuses indicating a permit is complete/closed
COMPLETED_STATUSES = {"Complete", "Closed"}
