###############################################################################
# Read Met Office radar rainfall data for DAFNI workflow
# Amy Green, Robin Wardle
# May 2022
###############################################################################

###############################################################################
# Python libraries
###############################################################################
import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
import io
import tqdm

###############################################################################
# Constants
###############################################################################
EA_ROOT_URL = "http://environment.data.gov.uk/flood-monitoring"
EA_REQUEST_STATIONS = "/id/stations?parameter=rainfall"
EA_REQUEST_GAUGES_15M = "/id/measures/{id}-rainfall-tipping_bucket_raingauge-t-15_min-mm/readings?parameter=rainfall&startdate={startDate}&enddate={endDate}"
EA_REQUEST_ARCHIVE = "/archive/readings-full-{date}.csv"

###############################################################################
# Parameters
###############################################################################

# Dates for files
start_date = os.getenv("RUN_START_DATE", "2023-06-20")
end_date = os.getenv("RUN_END_DATE", "2023-06-30")

# Bounding box for data
# e_l, n_l, e_u, n_u = [355000, 534000, 440000, 609000]
e_l = os.getenv("BB_E_L", 355000)
n_l = os.getenv("BB_N_L", 534000)
e_u = os.getenv("BB_E_U", 440000)
n_u = os.getenv("BB_N_U", 609000)
bbox = [e_l, e_u, n_l, n_u]

# Output paths to save files
root_path = os.getenv("DATA_PATH", "./data")
output_path = os.path.join(root_path, "outputs")
output_path = os.path.join(output_path, "EA")
os.makedirs(output_path, exist_ok=True)
output_path_15min = os.path.join(output_path, "15min")
os.makedirs(output_path_15min, exist_ok=True)


###############################################################################
# Download the data
###############################################################################

# Get list of rainfall stations
root_url = EA_ROOT_URL
response = requests.get(root_url + EA_REQUEST_STATIONS)
r = response.json()["items"]
df = pd.json_normalize(r)

# Get stations in area
extent_stations = df.loc[(df.northing > n_l) & (df.northing < n_u) & (df.easting > e_l) & (df.easting < e_u)]
station_ids = extent_stations.stationReference.to_list()
names = np.array(extent_stations.stationReference + "_" + extent_stations.easting.astype(int).astype(
    str) + "_" + extent_stations.northing.astype(int).astype(str) + ".csv")

now = datetime.now()
# use real-time API if possible (last 28 days)
if now - pd.to_datetime(start_date) < pd.Timedelta("28d"):
    for i, station in tqdm.tqdm(enumerate(station_ids)):
        api_path = EA_ROOT_URL + EA_REQUEST_GAUGES_15M
        api_path = api_path.replace("{id}", station)
        api_path = api_path.replace("{startDate}", start_date)
        api_path = api_path.replace("{endDate}", end_date)
        api_path = api_path.replace("{startTime}", start_date)

        try:

            response = requests.get(api_path)
            r = response.json()["items"]
            df = pd.json_normalize(r)
            if len(df) > 0:
                data = pd.Series(df.value.values, index=pd.to_datetime(df.dateTime))
                data.to_csv(os.path.join(output_path, names[i]))
        except:
            print(station, "not worked.")

# if not use historical API (seems to only work for last year- not very historical)
else:
    dates = pd.date_range(start_date, end_date)
    iids = np.array(extent_stations.measures.str[0].str["@id"])

    for date_ts in tqdm.tqdm(dates):
        date = str(date_ts).split(" ")[0]
        api_path = EA_ROOT_URL + EA_REQUEST_ARCHIVE
        api_path = api_path.replace("{date}", str(date))
        r = requests.get(api_path)
        full_data = []
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
            full_data.append(df[[measure in iids for measure in df.measure]])
    full_data = pd.concat(full_data).groupby("stationReference")

    for i, station in tqdm.tqdm(enumerate(station_ids)):
        try:
            (full_data.get_group(station).value).to_csv(os.path.join(output_path, names[i])) # check units? Is this mm or mm/h because if it is mm it needs multiplying by 4?
        except:
            print(station, "not worked.")
# Filled in data incase missing values (don't think there is but just in case)
new_timestamp = pd.date_range(
    pd.to_datetime(start_date),
    pd.to_datetime(end_date) + pd.Timedelta(1, "d"),
    freq=str(15 * 60) + "s", 
    tz="UTC"
)

for f in tqdm.tqdm(os.listdir(output_path)):
    if f.endswith(".csv"):
        tab = pd.read_csv(os.path.join(output_path, f), index_col=0)
        tab.index = pd.to_datetime(tab.index)

        filled_in = pd.Series(np.nan, index=new_timestamp)
        filled_in.loc[tab.index] = tab.iloc[:, 0].values

        filled_in.to_csv(os.path.join(output_path_15min, f))