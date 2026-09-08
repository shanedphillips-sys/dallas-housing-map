"""
City-of-Dallas land owned by faith CONGREGATIONS, across the three appraisal districts that
cover the city. Production build: writes the webmap layer and the report tables.

WHY THE METHOD DIFFERS BY COUNTY
--------------------------------
The three CADs do not carry the same fields, so the same protocol cannot be run on all
three. What each one actually provides:

                          Dallas CAD          Collin CAD         Denton protax
  religious BUILDING class  YES  bldg_cl        none               none
                            "CHURCH BUILDING"
  total-exemption flag      YES  totexempt=X    YES  EX-XV         none (only config
                                                                   flags: exemptionReset=0)
  homestead flag            YES  EXEMPTION_CD 1 YES  HS            none
  owner names               YES  ACCOUNT_INFO   YES  ownerName     YES (19 GB stream)
  ------------------------------------------------------------------------------------
  => method                 seed + linkage     name match          name match only,
                            + name sweep       anchored on         Tier A words only
                                               exemption

Dallas is the only county where a parcel can be identified WITHOUT trusting a name, so it
gets the full protocol. Collin has no church class but does have a usable exemption, so a
name match there is still corroborated. Denton has neither, so it rests on the owner name
alone and is restricted to Tier A (unambiguous institutional words) -- the weakest evidence
of the three, and only ~2,300 city parcels, so the exposure is small.

DALLAS PROTOCOL
  0. PUBLIC SCREEN -- drop governmental / quasi-governmental owners. DCAD has no ownership
       sector flag (its SPTD "Govt Owned" subcodes cover ~150 parcels), so this is a name
       pattern built by reading the ranked list of every tax-exempt owner in the county.
       It carries most of the weight: 84.9% of all tax-exempt land in the city is public,
       the City of Dallas alone holding 30,995 exempt acres.
  1. SEED   -- CHURCH BUILDING class AND totally exempt. Non-exempt church buildings are
       dropped (typically former churches sold on).
  2/3. LINK -- every other exempt parcel held by a seed owner: the vacant lot next door,
       the parking lot, the parsonage, the land banked for later.
  4. SWEEP  -- remaining exempt, non-public, non-homestead parcels whose owner name carries
       a faith vocabulary word.

VOCABULARY -- two tiers, cut on measured false-positive rates in DCAD:
  Tier A  institutional words that essentially never appear in a personal name.
  Tier B  words that are also common personal/place names; exempt + non-homestead only.
  Never   JESUS (1,783 owners, 50% homestead -- the Spanish given name), BETH (82%
          homestead), SAN/SANTA, LORD, TRINITY (the river), SHILOH. Real congregations
          using those words are caught by their Tier A words instead.

CATEGORIES -- the set is split, not silently filtered, so every acre stays documented:
  Congregation                     -> the YIGBY-relevant set, written to the map
  School / college / university    -> excluded per project decision
  Cemetery / funeral               -> excluded; burial ground cannot be built on
  Faith institution                -> hospital, senior living, shelter, community centre
Guards found by reading what each screen actually caught: COLLEGE PARK is a Dallas place
name (College Park Baptist Church); a parcel DCAD classes CHURCH BUILDING is a worship site
even when a school shares it (the Catholic parish campuses); VILLAGE would swallow The
Village Church, GOODWILL would swallow Goodwill Baptist Church, CRUSADE would swallow
Crusade For Christ Church.

KNOWN GAPS
  * The gpkg is a filtered extract and drops some City-of-Dallas parcels -- 221 of 2,546
    Denton records have no polygon, costing 2 identified Denton congregations / 6.7 acres.
  * Only the OWNER is known, not the use. A congregation that MEETS in a building it does
    not own (storefront and strip-mall churches, common in Dallas) is invisible here.
  * Denton cannot be exemption-checked at all, so its handful of parcels rest on name only.

OUTPUT
  data/faith_parcels.geojson          webmap layer (congregations only)
  output/faith_summary.csv            citywide totals
  output/faith_by_county.csv          method + yield per appraisal district
  output/faith_by_council.csv         parcels + acres per council district
  output/faith_zoning_districts.csv   parcels + acres per zoning district
  output/faith_owners.csv             per-owner roll-up
  output/faith_all_categories.csv     every matched parcel incl. the excluded categories
Read-only over every appraisal-district source.
"""
import json
import os
import re

import geopandas as gpd
import numpy as np
import pandas as pd

WEB = os.path.dirname(os.path.abspath(__file__))
GCS = (r"C:/Users/shane/OneDrive/Documents/Domain Consulting/Projects/"
       r"GDPC - Dallas Housing Report/GDPC Claude Stuff")
BASE = (r"C:/Users/shane/OneDrive/Documents/Domain Consulting/Projects/"
        r"GDPC - Dallas Housing Report")
GPKG = os.path.join(GCS, "PARCEL_CORE_MERGED.gpkg")
CERT = os.path.join(GCS, "DCAD2025_CERTIFIED")
COLLIN_CSV = os.path.join(BASE, "Collin_CAD_Appraisal_Data_-_2025_20260520.csv")
DENTON_CACHE = os.path.join(WEB, "data", "denton_dallas_owners.json")
OUTDIR = os.path.join(WEB, "output")
AC = 43_560.0

# ---------------------------------------------------------------- match vocabulary
TIER_A = [
    r"CHURCH(?:ES)?", r"IGLESIA", r"IGREJA", r"TEMPLO", r"BAPTIST", r"METHODIST", r"CATHOLIC",
    r"PRESBYTERIAN", r"PRESBYTERY", r"LUTHERAN", r"EPISCOPAL", r"SYNAGOGUE", r"MOSQUE",
    r"MASJID", r"ISLAMIC", r"CONGREGATION", r"CONGREGACION", r"DIOCESE", r"ARCHDIOCESE",
    r"MINISTRIES", r"TABERNACLE", r"CATHEDRAL", r"PENTECOSTAL", r"PENTECOSTES", r"GOSPEL",
    r"JEHOVAH", r"KINGDOM\s+HALL", r"CHABAD", r"TORAH", r"BUDDHIST", r"HINDU", r"SIKH",
    r"GURDWARA", r"UNITARIAN", r"ADVENTIST", r"NAZARENE", r"APOSTOLIC", r"MISSIONARY",
    r"MISIONERA", r"LATTER\s*-?\s*DAY", r"ASSEMBLY\s+OF\s+GOD", r"ASAMBLEA", r"WORSHIP",
    # EVANGEL... but NOT Evangelina/Evangeline, both common Spanish given names here
    r"ADORACION", r"EVANGEL(?!IN)\w*", r"REDEEMER", r"SAVIOR", r"DISCIPLES", r"CALVARY",
    r"COGIC", r"DELIVERANCE", r"AME", r"CME", r"SYNOD", r"ORTHODOX", r"COPTIC", r"MENNONITE",
    # Emanu-El (the synagogue) only -- a bare EMANU\w* swallows the given name Emanuel
    r"SHEARITH", r"EMANU\s*-?\s*EL", r"TIFERET", r"ANSHAI", r"AGUDAS", r"KEHILLAH", r"JEWISH",
    r"QURAN", r"CRISTIAN[AO]", r"SEMINARY", r"FELLOWSHIP", r"ZION", r"CANAAN",
    r"MOUNT\s+CARMEL", r"GETHSEMANE", r"PRAISE", r"GOD", r"CHRIST",
]
TIER_B = [
    r"TEMPLE", r"FAITH", r"CHAPEL", r"HOLY", r"BETHEL", r"MINISTRY", r"MINISTERIO",
    r"MISSION", r"ANTIOCH", r"EBENEZER", r"BIBLE", r"ISLAM", r"MUSLIM", r"UNITY",
    r"MEDITATION", r"BAUTISTA", r"SANCTUARY", r"REVIVAL", r"SPIRITUAL",
    r"SAINT", r"GRACE", r"CHRISTIAN", r"EMMANUEL", r"IMMANUEL", r"BETHANY", r"LDS",
    r"PARISH", r"BISHOP", r"PROPHETIC", r"BUDDHA", r"DHARMA", r"ASHRAM", r"MANDIR",
    r"JAIN", r"QUAKER", r"FRIENDS\s+MEETING", r"ABUNDANT\s+LIFE", r"SANTUARIO",
    r"PARROQUIA", r"HEBREW", r"JUDAIC", r"VEDANTA", r"BAHAI", r"ZOROASTRIAN",
]
# Government / quasi-government. Matched on the LEGAL owner and kept specific: DCAD writes
# municipalities surname-first ("DALLAS CITY OF"), so CITY OF is matched only at the end of
# a name, never bare -- otherwise CITY OF HOPE AND RESTORATION LIFE would be thrown out.
PUBLIC = [
    r"CITY OF$", r"^CITY OF DALLAS", r"CITY COUNTY", r"\bCOUNTY OF\b", r"^DALLAS COUNTY",
    r"\bTOWN OF$", r"\bISD\b", r"\bI S D\b", r"SCHOOL DISTRICT", r"INDEPENDENT SCHOOL",
    r"UNITED STATES", r"^U S ", r"^U S A$", r"\bUSA$", r"\bFEDERAL\b",
    r"^STATE OF", r"STATE OF$", r"TEXAS STATE OF", r"\bTXDOT\b", r"TEXAS DEPARTMENT",
    r"HOUSING AUTHORITY", r"RAPID TRANSIT", r"\bDART\b",
    r"BOARD OF REG", r"UNIV OF TX", r"UNIVERSITY OF TEXAS", r"UNIVERSITY OF NORTH TX",
    r"TEXAS A M\b", r"TEXAS WOMANS", r"DALLAS COLLEGE",
    r"RIVER AUTHORITY", r"\bLEVEE\b", r"\bFLOOD\b", r"IRRIGATION DISTRICT",
    r"UTILITY DIST", r"MUNICIPAL UTILITY", r"PUBLIC FACILITY CORP", r"HOSPITAL DIST",
    r"\bCHARTER\b", r"UPLIFT EDUCATION", r"SCHOOLS INC", r"POSTAL SERVICE",
    r"PUBLIC SCHOOLS", r"BASIN PREPARATORY", r"LAIQUE", r"LIFESCHOOL",
]
CEMETERY = [r"CEMETER\w*", r"CEMETAR\w*", r"MEMORIAL PARK", r"MEMORIAL GARDEN", r"FUNERAL",
            r"MORTUAR\w*", r"\bBURIAL\b", r"MAUSOLEUM", r"COLUMBARIUM"]
SCHOOL = [r"\w*SCHOOL\w*", r"ACADEM\w*", r"\bCOLLEGE(?!\s+PARK)\w*", r"UNIVERSIT\w*",
          r"SEMINAR\w*", r"\bINSTITUTE\b", r"PREPARATORY", r"MONTESSORI",
          r"CHRIST FOR THE NATIONS", r"BIBLE INSTITUTE", r"BIBLE COLLEGE"]
INSTITUTION = [
    r"HOSPITAL\w*", r"MEDICAL CENTER", r"\bMEDICAL\b", r"HEALTH SYSTEM",
    r"RETIREMENT", r"NURSING", r"ASSISTED LIVING", r"COMMUNITIES SERVICES",
    r"PRESBYTERIAN VILLAGE", r"HOSPICE",
    r"BENEVOLENCE\w*", r"RESCUE MISSION", r"SALVATION ARMY", r"AUSTIN STREET",
    r"24 HOUR CLUB", r"VOICE OF HOPE", r"FOOD BANK", r"CRISIS CENTER",
    r"COMMUNITY CENTER", r"CAMPUS FACILITIES", r"\bYMCA\b", r"\bYWCA\b",
    r"PRINCE MINISTRIES", r"TELEVISION", r"BROADCAST\w*",
]
# Tier A words that also work as a personal name in Dallas records ("CHRIST GEORGE CHARLES",
# "CATHOLIC MELCHI"). Every other Tier A word is itself proof the name is an organisation.
PERSON_RISKY = {r"CHRIST", r"NAZARENE", r"CATHOLIC", r"ZION", r"CANAAN"}
ORG_MARKER = [t for t in TIER_A if t not in PERSON_RISKY] + [
    r"UNIVERSIT\w*", r"COLLEGE\w*", r"SEMINARY", r"ACADEM\w*", r"SCHOOL\w*", r"CEMETER\w*",
    r"HOSPITAL\w*", r"VILLAGE", r"BENEVOLENCE\w*", r"INSTITUTE", r"TEMPLE", r"CHAPEL",
    r"MINISTR\w*", r"MINISTER\w*", r"MINISTERIO", r"MISSION\w*", r"CENTER", r"CENTRE",
    r"CENTRO", r"SOCIETY", r"FOUNDATION", r"\bINC\b", r"\bLLC\b", r"\bLP\b", r"\bLTD\b",
    r"CORP\w*", r"COMPANY", r"ASSN", r"ASSOCIATION", r"PROPERTIES", r"GROUP", r"TRUST",
    r"MEMORIAL", r"COUNCIL", r"CONFERENCE", r"\bORG\b", r"HOUSE\s+OF", r"OUTREACH",
    r"INTERNATIONAL", r"INTERN\b", r"BIBLE",
]
RE_A = re.compile(r"\b(?:" + "|".join(TIER_A) + r")\b")
RE_B = re.compile(r"\b(?:" + "|".join(TIER_B) + r")\b")
RE_PUB = re.compile("|".join(PUBLIC))
RE_CEM = re.compile("|".join(CEMETERY))
RE_SCH = re.compile("|".join(SCHOOL))
RE_INST = re.compile("|".join(INSTITUTION))
RE_ORG = re.compile(r"\b(?:" + "|".join(ORG_MARKER) + r")\b")
RE_INITIAL = re.compile(r"(?:^|\s)[A-Z](?:\s|$)")


def looks_personal(name):
    """DCAD writes owners surname-first, so the personal-name failure mode is
    "CHRIST GEORGE CHARLES" / "LOPEZ EVANGELINA": few words, or a bare middle initial, or
    an "&" joining spouses -- and never an organisational word."""
    if not name or RE_ORG.search(name):
        return False
    return len(name.split()) <= 3 or "&" in name or bool(RE_INITIAL.search(name))


def log(m):
    print(m, flush=True)


def norm(s):
    s = re.sub(r"[^A-Z0-9 ]+", " ", str(s).upper())
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- parcels
log("Loading City-of-Dallas parcels ...")
g = gpd.read_file(GPKG, columns=["ACCOUNT_NUM", "county", "totexempt", "prop_cl", "sptbcode",
                                 "bldg_cl", "area_feet", "dacouncil", "st_num", "st_name",
                                 "st_type", "COM_GROSS_BLDG_AREA", "RES_TOT_LIVING_AREA_SF"])
g = g.reset_index(drop=True)
g["cty"] = g["county"].str.replace(" COUNTY", "", regex=False)
g["acres"] = pd.to_numeric(g["area_feet"], errors="coerce") / AC
g["church_bldg"] = g.bldg_cl.astype(str).str.upper().str.contains("CHURCH", na=False)
g["vacant"] = g.prop_cl.fillna("").str.upper().str.contains("VACANT")
n = len(g)
log(f"  {n:,} parcels  ({g.cty.value_counts().to_dict()})")

legal = np.full(n, "", dtype=object)     # legal owner (screens + person test)
full = np.full(n, "", dtype=object)      # legal owner + business/property name (matching)
exempt = np.zeros(n, dtype=bool)
hstead = np.zeros(n, dtype=bool)
impr = np.zeros(n)          # improvement value -- the vacancy test
landv = np.zeros(n)         # land value -- fallback ratio when floor area is unusable
bsf = np.zeros(n)           # building floor area -- the FAR numerator

# --- Dallas CAD -------------------------------------------------------------
ai = pd.read_csv(os.path.join(CERT, "ACCOUNT_INFO.CSV"),
                 usecols=["ACCOUNT_NUM", "OWNER_NAME1", "OWNER_NAME2", "BIZ_NAME"],
                 dtype=str, low_memory=False).drop_duplicates("ACCOUNT_NUM").set_index("ACCOUNT_NUM")
ai["lg"] = (ai.OWNER_NAME1.fillna("") + " " + ai.OWNER_NAME2.fillna("")).map(norm)
ai["fl"] = (ai.lg + " " + ai.BIZ_NAME.fillna("").map(norm)).str.strip()
is_dal = g.cty.eq("DALLAS").to_numpy()
legal[is_dal] = g.loc[is_dal, "ACCOUNT_NUM"].map(ai["lg"]).fillna("").to_numpy()
full[is_dal] = g.loc[is_dal, "ACCOUNT_NUM"].map(ai["fl"]).fillna("").to_numpy()
exempt[is_dal] = g.loc[is_dal, "totexempt"].astype(str).str.strip().str.upper().eq("X").to_numpy()
hs_acct = set(pd.read_csv(os.path.join(CERT, "ACCT_EXEMPT_VALUE.CSV"),
                          usecols=["ACCOUNT_NUM", "EXEMPTION_CD"], dtype=str)
              .query('EXEMPTION_CD == "1"').ACCOUNT_NUM)
hstead[is_dal] = g.loc[is_dal, "ACCOUNT_NUM"].isin(hs_acct).to_numpy()
ay = pd.read_csv(os.path.join(CERT, "ACCOUNT_APPRL_YEAR.CSV"),
                 usecols=["ACCOUNT_NUM", "IMPR_VAL", "LAND_VAL"], dtype=str,
                 low_memory=False).drop_duplicates("ACCOUNT_NUM").set_index("ACCOUNT_NUM")
for _c in ("IMPR_VAL", "LAND_VAL"):
    ay[_c] = pd.to_numeric(ay[_c], errors="coerce")
impr[is_dal] = g.loc[is_dal, "ACCOUNT_NUM"].map(ay.IMPR_VAL).fillna(0).to_numpy()
landv[is_dal] = g.loc[is_dal, "ACCOUNT_NUM"].map(ay.LAND_VAL).fillna(0).to_numpy()
bsf[is_dal] = (pd.to_numeric(g.loc[is_dal, "COM_GROSS_BLDG_AREA"], errors="coerce").fillna(0)
               + pd.to_numeric(g.loc[is_dal, "RES_TOT_LIVING_AREA_SF"], errors="coerce").fillna(0)).to_numpy()

# --- Collin CAD -------------------------------------------------------------
col = pd.read_csv(COLLIN_CSV, usecols=["propID", "ownerName", "ownerNameAddtl", "dbaName",
                                       "exemptCodes", "currValImprv", "currValLand",
                                       "imprvMainArea"], dtype=str, low_memory=False)
col["pid"] = pd.to_numeric(col.propID, errors="coerce").astype("Int64")
col["lg"] = (col.ownerName.fillna("") + " " + col.ownerNameAddtl.fillna("")).map(norm)
col["fl"] = (col.lg + " " + col.dbaName.fillna("").map(norm)).str.strip()
col = col.dropna(subset=["pid"]).drop_duplicates("pid").set_index("pid")
is_col = g.cty.eq("COLLIN").to_numpy()
cpid = pd.to_numeric(g.loc[is_col, "ACCOUNT_NUM"].str[4:], errors="coerce").astype("Int64")
legal[is_col] = cpid.map(col["lg"]).fillna("").to_numpy()
full[is_col] = cpid.map(col["fl"]).fillna("").to_numpy()
ccodes = cpid.map(col["exemptCodes"]).fillna("").str.upper()
exempt[is_col] = ccodes.str.contains("EX-XV", regex=False).to_numpy()   # the charitable code
hstead[is_col] = ccodes.str.contains(r"\bHS\b", regex=True).to_numpy()

# --- Denton (cached owner names; NO exemption codes exist in the export) -----
is_den = g.cty.eq("DENTON").to_numpy()
if os.path.exists(DENTON_CACHE):
    den = json.load(open(DENTON_CACHE))
    dmap = {int(k): norm(" ".join(v.get("owners") or [])) for k, v in den.items()}
    dpid = pd.to_numeric(g.loc[is_den, "ACCOUNT_NUM"].str[4:], errors="coerce").astype("Int64")
    legal[is_den] = dpid.map(dmap).fillna("").to_numpy()
    full[is_den] = legal[is_den]
    # values/floor area come from the in-repo Denton slim, which the owner cache omits
    slim = json.load(open(os.path.join(WEB, "data", "denton_dallas_slim.json")))
    sv = {int(r["pID"]): r for r in slim if r.get("pID") is not None}
    impr[is_den] = dpid.map(lambda k: float(sv.get(k, {}).get("valStructure") or 0)).to_numpy()
    landv[is_den] = dpid.map(lambda k: float(sv.get(k, {}).get("valLand") or 0)).to_numpy()
    bsf[is_den] = dpid.map(lambda k: float(sv.get(k, {}).get("imprvTotalArea") or 0)).to_numpy()
else:
    log(f"  !! Denton owner cache missing ({DENTON_CACHE}); run build_denton_owners.py")

g["legal_owner"] = legal
g["owner_full"] = full
g["exempt"] = exempt
g["homestead"] = hstead
g["impr_val"] = impr
g["land_val"] = landv
g["bldg_sf"] = bsf
g["public"] = g.legal_owner.str.contains(RE_PUB, regex=True, na=False)
g["personal"] = g.legal_owner.map(looks_personal)
a_hit = g.owner_full.str.contains(RE_A, regex=True, na=False)
b_hit = g.owner_full.str.contains(RE_B, regex=True, na=False)

# ---------------------------------------------------------------- per-county selection
src = pd.Series("", index=g.index, dtype=object)

# --- DALLAS: seed -> owner linkage -> name sweep -----------------------------
dal = g.cty.eq("DALLAS")
seed = dal & g.church_bldg & g.exempt & ~g.public & ~g.homestead
seed_owners = set(g.loc[seed & g.legal_owner.ne(""), "legal_owner"])
linked = dal & g.exempt & ~g.public & ~g.homestead & g.legal_owner.isin(seed_owners) & ~seed
sweep = (dal & g.exempt & ~g.public & ~g.homestead & ~g.personal & ~seed & ~linked
         & (a_hit | b_hit))
src[seed] = "Dallas: church building + exempt"
src[linked] = "Dallas: owner linked to a church-building parcel"
src[sweep] = "Dallas: owner name + exempt"

# --- COLLIN: name match anchored on the EX-XV exemption ----------------------
colm = (g.cty.eq("COLLIN") & g.exempt & ~g.public & ~g.homestead & ~g.personal
        & (a_hit | b_hit))
src[colm] = "Collin: owner name + exempt (no church class)"

# --- DENTON: name match only, Tier A -- no exemption data exists -------------
denm = g.cty.eq("DENTON") & ~g.public & ~g.personal & a_hit
src[denm] = "Denton: owner name only (no exemption data)"

g["source"] = src
f = g[g.source.ne("")].copy()

# ---------------------------------------------------------------- categorise
bc = f.bldg_cl.astype(str).str.upper()
owner_sch = f.legal_owner.str.contains(RE_SCH, regex=True, na=False)
prop_sch = f.owner_full.str.contains(RE_SCH, regex=True, na=False) | bc.str.contains("SCHOOL", na=False)
is_cem = ((f.owner_full.str.contains(RE_CEM, regex=True, na=False)
           | bc.str.contains("FUNERAL", na=False)) & ~f.church_bldg)
is_sch = (owner_sch | (prop_sch & ~f.church_bldg)) & ~is_cem
is_inst = f.legal_owner.str.contains(RE_INST, regex=True, na=False) & ~is_cem & ~is_sch
f["category"] = np.where(is_cem, "Cemetery / funeral",
                  np.where(is_sch, "School / college / university",
                   np.where(is_inst, "Faith institution (hospital / senior / shelter)",
                            "Congregation")))
cong = f[f.category.eq("Congregation")].copy()

# ---------------------------------------------------------------- development status
# Vacant vs Developed, on the improvement value alone: any assessed structure makes a parcel
# Developed. An earlier cut split Developed further by floor-area ratio, but DCAD does not
# MEASURE most exempt buildings -- it records them as a 100 sq ft placeholder, which covered
# 171 of these parcels, 156 of them classed CHURCH BUILDING. A FAR was therefore unavailable
# for precisely the buildings this study is about, so the distinction was dropped rather than
# rested on a value-ratio proxy. bldg_sf is kept for the popup, flagged where DCAD actually
# measured it.
cong["devcat"] = np.where(cong.impr_val <= 0, "Vacant", "Developed")
cong["bldg_sf_known"] = cong.bldg_sf > 100
# Everything downstream (county, council and zoning tables) uses the same definition of
# vacant, rather than the prop_cl text flag it started from.
cong["vacant"] = cong.devcat == "Vacant"

# ---------------------------------------------------------------- zoning + council
zon = gpd.read_file(os.path.join(WEB, "data", "zoning.geojson"))[
    ["zone_dist", "zone_norm", "category", "geometry"]].to_crs(2276)
cou = gpd.read_file(os.path.join(WEB, "data", "council.geojson"))[["district", "geometry"]].to_crs(2276)
pts = gpd.GeoDataFrame({"i": cong.index},
                       geometry=cong.to_crs(2276).representative_point().values, crs=2276)
zj = gpd.sjoin(pts, zon, how="left", predicate="within").drop_duplicates("i").set_index("i")
cong["zone_dist"] = zj["zone_dist"].reindex(cong.index).values
cong["zone_norm"] = zj["zone_norm"].reindex(cong.index).fillna("(no zoning match)").values
cong["zone_cat"] = zj["category"].reindex(cong.index).fillna("(no zoning match)").values
cj = gpd.sjoin(pts, cou, how="left", predicate="within").drop_duplicates("i").set_index("i")
cong["council"] = cj["district"].reindex(cong.index).values
cong["council"] = cong["council"].fillna(cong["dacouncil"].replace("0", np.nan))

# ---------------------------------------------------------------- tables
os.makedirs(OUTDIR, exist_ok=True)
METHOD = {
    "DALLAS": "church-building seed + owner linkage + name sweep (all exempt-anchored)",
    "COLLIN": "owner name + EX-XV exemption (no church class in Collin CAD)",
    "DENTON": "owner name only, Tier A words (no exemption codes in the protax export)",
}
by_cty = (cong.groupby("cty").agg(parcels=("acres", "size"), acres=("acres", "sum"),
                                  vacant_parcels=("vacant", "sum"),
                                  church_bldg=("church_bldg", "sum"),
                                  owners=("legal_owner", "nunique")).round(1))
by_cty["method"] = [METHOD.get(i, "") for i in by_cty.index]
by_cty = by_cty.sort_values("acres", ascending=False)
by_cty.to_csv(os.path.join(OUTDIR, "faith_by_county.csv"))
log("\n================ METHOD AND YIELD BY APPRAISAL DISTRICT ================")
log(by_cty[["parcels", "acres", "vacant_parcels", "church_bldg", "owners"]].to_string())
for k, v in METHOD.items():
    log(f"  {k:7} {v}")

log("\n================ DEVELOPMENT STATUS (congregation parcels) ================")
log((cong.groupby("devcat").agg(parcels=("acres", "size"), acres=("acres", "sum"))
     .round(1).reindex(["Vacant", "Developed"])).to_string())
log(f"  floor area actually measured by DCAD: {int(cong.bldg_sf_known.sum()):,} of "
    f"{int((cong.impr_val > 0).sum()):,} built parcels -- the rest carry DCAD's 100 sq ft "
    f"placeholder for exempt buildings it never measured")

log("\n================ CATEGORY SPLIT (all counties) ================")
log(f.groupby("category").agg(parcels=("acres", "size"), acres=("acres", "sum"))
    .round(1).sort_values("acres", ascending=False).to_string())

k3 = cong.legal_owner.map(lambda s: " ".join(str(s).split()[:3]))
summ = pd.DataFrame([{
    "parcels": len(cong), "acres": round(cong.acres.sum(), 1),
    "sq_mi": round(cong.acres.sum() / 640, 2),
    "distinct_owner_names": cong.legal_owner.nunique(),
    "distinct_congregations": k3.nunique(),
    "with_church_building": int(cong.church_bldg.sum()),
    "vacant_parcels": int((cong.devcat == "Vacant").sum()),
    "vacant_acres": round(cong.loc[cong.devcat == "Vacant", "acres"].sum(), 1),
    "developed_parcels": int((cong.devcat == "Developed").sum()),
    "developed_acres": round(cong.loc[cong.devcat == "Developed", "acres"].sum(), 1),
    "dallas_parcels": int((cong.cty == "DALLAS").sum()),
    "collin_parcels": int((cong.cty == "COLLIN").sum()),
    "denton_parcels": int((cong.cty == "DENTON").sum()),
}])
summ.to_csv(os.path.join(OUTDIR, "faith_summary.csv"), index=False)
log("\n================ COMBINED -- ALL LAND IN THE CITY OF DALLAS ================")
for k, v in summ.iloc[0].items():
    log(f"  {k:26} {v:>12,}")

t = cong.groupby("council", dropna=False).agg(parcels=("acres", "size"), acres=("acres", "sum"))
t["vacant_parcels"] = cong[cong.vacant].groupby("council", dropna=False).size().reindex(t.index).fillna(0).astype(int)
t["vacant_acres"] = cong[cong.vacant].groupby("council", dropna=False).acres.sum().reindex(t.index).fillna(0)
t = t.round(1).sort_values("acres", ascending=False)
t.to_csv(os.path.join(OUTDIR, "faith_by_council.csv"))
log("\n================ BY COUNCIL DISTRICT ================")
log(t.to_string())

zt = (cong.groupby(["zone_norm", "zone_cat"], dropna=False)
        .agg(parcels=("acres", "size"), acres=("acres", "sum")).reset_index())
zt["pct_acres"] = 100 * zt.acres / zt.acres.sum()
zt = zt.sort_values("acres", ascending=False).round({"acres": 1, "pct_acres": 2})
zt.to_csv(os.path.join(OUTDIR, "faith_zoning_districts.csv"), index=False)
log("\n================ BY ZONING DISTRICT ================")
log(zt.to_string(index=False))

(cong.assign(o=cong.legal_owner.str.title())
     .groupby("o").agg(parcels=("acres", "size"), acres=("acres", "sum")).round(1)
     .sort_values("acres", ascending=False)).to_csv(os.path.join(OUTDIR, "faith_owners.csv"))
f.drop(columns="geometry").to_csv(os.path.join(OUTDIR, "faith_all_categories.csv"), index=False)

# ---------------------------------------------------------------- webmap layer
out = cong[["ACCOUNT_NUM", "legal_owner", "owner_full", "cty", "source", "exempt",
            "church_bldg", "vacant", "devcat", "bldg_sf", "bldg_sf_known", "acres",
            "prop_cl", "zone_dist", "zone_norm", "zone_cat", "council", "st_num", "st_name",
            "st_type", "geometry"]].copy()
out["address"] = ((out.st_num.fillna("").astype(str).str.strip() + " "
                   + out.st_name.fillna("").str.strip() + " "
                   + out.st_type.fillna("").str.strip())
                  .str.replace(r"\s+", " ", regex=True).str.strip().str.title())
out = out.drop(columns=["st_num", "st_name", "st_type"])
out["acres"] = out.acres.round(3)
out["bldg_sf"] = out.bldg_sf.round(0)
out["owner"] = out.legal_owner.str.title()
out = out.drop(columns=["legal_owner", "owner_full"]).to_crs(4326)
dst = os.path.join(WEB, "data", "faith_parcels.geojson")
out.to_file(dst, driver="GeoJSON")
log(f"\nwrote {dst}  ({len(out):,} features, {os.path.getsize(dst) / 1e6:.1f} MB)")
log(f"wrote {OUTDIR}\\faith_summary.csv, faith_by_county.csv, faith_by_council.csv,")
log(f"      faith_zoning_districts.csv, faith_owners.csv, faith_all_categories.csv")
