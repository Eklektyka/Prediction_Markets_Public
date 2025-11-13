library(readxl)
setwd("~/Documents/Research/PredictionMarketsPublic/")

ois_data <- read_xlsx('data/OIS_Kalshi_Comparison_Rates.xlsx')
ois_data <- type.convert(ois_data, as.is = TRUE)

kalshi_data <- read_csv('data/daily_distribution_data_isotonic/daily_distributions_fed_levels.csv')
kalshi_data <- kalshi_data %>%
  group_by(date, contract_preamble, expiry_date) %>%
  summarise(
    mean     = sum(probability * strike, na.rm = TRUE) / sum(probability, na.rm = TRUE),
    median   = weightedMedian(strike, w = probability, na.rm = TRUE, interpolate = FALSE),
    mode = fmode(strike, w = probability, na.rm = TRUE, ties='first'),
    skewness = weightedGMSkew(strike, w = probability, na.rm = TRUE),
    kurtosis = DescTools::Kurt(strike, w = probability, na.rm = TRUE),
    variance = sum(probability * (strike - (sum(probability * strike) / sum(probability)))^2, na.rm = TRUE) / sum(probability, na.rm = TRUE),
    .groups = "drop"
  )
