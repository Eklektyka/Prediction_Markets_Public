# We're trying to figure out what's happening to some of the CPI data

setwd('~/Documents/Research/PredictionMarketsPublic')

cpi_trades <- read.csv('data/trade_level_data/trade_level_data_headline_cpi_releases.csv')

# let's look at an example I know disagrees with the Kalshi website first, Dec 2023


dec23_trades <- cpi_trades %>% filter(grepl("^CPIYOY-23DEC", ticker))


# There are lots of trades at the start of the sample in the lower bins, but they don't appear?

dec23_dec18_trades <- dec23_trades %>% filter(as_date(ymd_hms(created_time)) == as.Date('2023-12-18'))



###### Look at distribution data

cpi_daily <- read.csv('data/daily_distribution_data/daily_distributions_headline_cpi_releases.csv')
cpi_daily_moments <- read.csv('data/daily_moments_data/daily_moments_headline_cpi_releases.csv')
