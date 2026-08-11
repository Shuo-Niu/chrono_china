from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERMEDIATE_DIR = DATA_DIR / "intermediate"
PROCESSED_DIR = DATA_DIR / "processed"
QA_DIR = DATA_DIR / "qa"

TGAZ_INDEX_URL = (
    "https://raw.githubusercontent.com/cga-harvard/tgaz/master/"
    "data/csv/tgaz_chgis_2016-07-06.csv"
)
TGAZ_INDEX_README_URL = (
    "https://raw.githubusercontent.com/cga-harvard/tgaz/master/data/csv/readme.md"
)
TGAZ_DETAIL_URL = "https://tgaz.fudan.edu.cn/tgaz/placename/json/{tgaz_id}"
GEONAMES_CN_URL = "https://download.geonames.org/export/dump/CN.zip"
GEONAMES_README_URL = "https://download.geonames.org/export/dump/readme.txt"
GEONAMES_ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

TGAZ_INDEX_PATH = RAW_DIR / "tgaz_index" / "tgaz_chgis_2016-07-06.csv"
TGAZ_INDEX_README_PATH = RAW_DIR / "tgaz_index" / "readme.md"
TGAZ_INDEX_MANIFEST_PATH = RAW_DIR / "tgaz_index" / "manifest.json"
GEONAMES_ZIP_PATH = RAW_DIR / "geonames" / "CN.zip"
GEONAMES_README_PATH = RAW_DIR / "geonames" / "readme.txt"
GEONAMES_ADMIN1_PATH = RAW_DIR / "geonames" / "admin1CodesASCII.txt"
GEONAMES_MANIFEST_PATH = RAW_DIR / "geonames" / "manifest.json"
TGAZ_DETAIL_DIR = RAW_DIR / "tgaz_detail"

REQUIRED_TGAZ_FIELDS = (
    "TGAZ_ID",
    "TGAZ_URI",
    "DATA_SRC",
    "NAME_SIM",
    "NAME_ENG",
    "BEG",
    "END",
    "OBJ_TYPE",
    "X",
    "Y",
    "TYPE_SIM",
    "TYPE_ENG",
    "PARTOF_ID",
    "PARTOF_SIM",
    "PARTOF_ENG",
)

ANCHOR_SPECS = (
    {"anchor_id": "beijing", "query": "北京", "display_name": "北京"},
    {"anchor_id": "xian", "query": "西安", "display_name": "西安"},
    {"anchor_id": "chengdu", "query": "成都", "display_name": "成都"},
    {"anchor_id": "qingdao", "query": "青岛", "display_name": "青岛"},
)

COUNTY_CANDIDATE_SPECS = (
    {"anchor_id": "qufu", "query": "曲阜", "display_name": "曲阜"},
    {"anchor_id": "linhai", "query": "临海", "display_name": "临海"},
    {"anchor_id": "shexian", "query": "歙县", "display_name": "歙县"},
)

NEGATIVE_CONTROL_SPEC = {
    "anchor_id": "urumqi_negative_control",
    "query": "乌鲁木齐",
    "display_name": "乌鲁木齐",
    "expected_coverage": "outside_source_scope",
}

DEFAULT_RADIUS_KM = 75.0
