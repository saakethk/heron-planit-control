# Data
Contains all data sources necessary for this project.

## Necessary Data Sources
- plant info
  - https://www.eia.gov/electricity/data/eia860m/
  - 343 power plants in florida (sufficient number)
- weather (temperature, humidity, conditions - raining, snowing, ect.) (realtime and historical)
  - https://open-meteo.com
  - https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview
- extreme weather events (flooding, lightning, wildfire) (realtime and historical)
  - historical: https://open-meteo.com
  - realtime: https://www.weatherapi.com, 
  - National Levee Database (NLD):
  - https://tidesandcurrents.noaa.gov
  - wildfire (NASA FIRMS)
- soil saturation
  - https://open-meteo.com
- wildlife sightings (potentially user-reported) (need to figure out)
- historical incident reports
  - https://www.osha.gov/severe-injury-reports
  - Event Codes can be used to filter: https://www.bls.gov/iif/definitions/occupational-injuries-and-illnesses-classification-manual.htm
  - [File containing the relevant codes for jbo site injuries related to environment or wildlife](incident_data/oiics_wildlife_environmental_codes_v201_v303.csv)