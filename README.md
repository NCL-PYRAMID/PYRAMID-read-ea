# PYRAMID-read-ea

## Reading in Environment Agency rain gauge data (15 min)
### Notes
- Intense QC code read in, not sure how easy that will be, I had to clone it off Github and change line 10 of code as got an error with a package, proabbly due to Python versions. Think the package needs updating on Github but not sure who is still in charge of maintaining it. Need ETCCDI data (available in example data for Intense QC)

### What does the code do?
- Download the data
- Try historic API
- Try real-time API
- Save data

### Outputs format
- `\root` folder path
  - `\EA` folder path (15 minute rain gauge data)
    - `<station-id>_<eastings>_<northings>.csv` - individual 15-minute gauge data for station `<station-id>`
    - `\15min` folder path (15 minute rain gauge data) with filled in timestamp
      - `<station-id>_<eastings>_<northings>.csv` - individual 15-minute gauge data for station `<station-id>`
