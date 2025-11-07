##################################
##   Kalshi Bid–Ask Processor   ##
##################################
# Author: Jared Dean Katz, Anthony M. Diercks
# Description:
#  Converts Kalshi daily bid–ask candlestick data (from Python scraper)
#  into daily PDFs and computes distributional moments.

library(tidyverse)
library(lubridate)
library(matrixStats)
library(DescTools)
library(collapse)


setwd('/Users/jaredkatz/Documents/Research/PredictionMarketsPublic')


# ------------------------
# Read and preprocess data
# ------------------------
read_bid_ask <- function(input_file, filter_large_spreads = T) {
  
  df <- read_csv(input_file)
  
  df <- df %>%
    mutate(
      date = as.Date(end_period_utc),
      # Extract event prefix and strike from market_ticker
      contract_preamble = str_extract(market_ticker, ".*(?=-T[^-]+$)"),
      strike_raw = str_extract(market_ticker, "(?<=-T)[^\\-]+$"),
      strike = as.numeric(str_replace_all(strike_raw, "−", "-")),
      # Midpoint between yes_bid and yes_ask close prices
      yes_price = (yes_bid_close + yes_ask_close) / 2
    )
  
  # If the flag is turned on, remove anything with a bid-ask spread of more than 15
  if(filter_large_spreads == TRUE) {
    
    df <- df %>% mutate(large_spread = abs(yes_bid_close - yes_ask_close) > 15)

    df <- df %>%
      arrange(series, event_ticker, market_ticker, end_period_utc) %>%
      group_by(series, event_ticker, market_ticker) %>%
      # keep only values from rows where large_spread == FALSE, NA otherwise
      mutate(
        last_good_bid = if_else(!large_spread, yes_bid_close, NA_real_),
        last_good_ask = if_else(!large_spread, yes_ask_close, NA_real_)
      ) %>%
      # carry the last good values forward within each group
      fill(last_good_bid, last_good_ask, .direction = "down") %>%
      # replace only where large_spread == TRUE (leave others untouched)
      mutate(
        yes_bid_close = if_else(large_spread & !is.na(last_good_bid), last_good_bid, yes_bid_close),
        yes_ask_close = if_else(large_spread & !is.na(last_good_ask), last_good_ask, yes_ask_close)
      ) %>%
      # drop helper columns and ungroup
      select(-last_good_bid, -last_good_ask) %>%
      ungroup()
    
  }
  
    df <- df %>% select(date, contract_preamble, strike, yes_price, volume, open_interest) %>%
    arrange(contract_preamble, strike, date)
  
  return(df)
}


#' Fill missing days in daily data with last known price (from a previous day)
#'
#' Ensures each valid contract_preamble and strike pair has data for every date in the full range.
#' Fills forward the last known price, sets daily volume to 0 on filled days,
#' and trims data outside the active contract period.
#'
#' @param df A data frame with columns: date, contract_preamble, strike, yes_price, daily_volume.
#' @return A data frame with missing dates filled and cleaned.
fill_dataless_days <- function(df) {
  
  # Get unique strike-preamble combinations that actually exist
  valid_combos <- df %>% select(contract_preamble, strike) %>% distinct()
  
  # Get full date range
  dates <- seq(min(df$date), max(df$date), by = "day")
  
  # Create full date range for only valid strike-preamble combos
  full_date_range <- valid_combos %>%
    crossing(date = dates)
  
  # Merge with current df
  df <- df %>% full_join(full_date_range) %>% 
    arrange(contract_preamble, strike, date)
  
  # get the contract expiry date
  df <- df %>%
    group_by(contract_preamble) %>%
    mutate(
      expiry_date = if (all(is.na(yes_price))) NA_Date_ else max(date[!is.na(yes_price)])
    ) %>%
    ungroup()
  
  # fill NA rows with last price and fill in 0 for daily volume on these days
  df <- df %>%
    group_by(contract_preamble, strike) %>%
    fill(yes_price, .direction = "down") %>%
    ungroup() %>% mutate(
      volume = ifelse(is.na(volume), 0, volume),
      open_interest = ifelse(is.na(open_interest), 0, open_interest)
      
    )
  
  # remove the rows at the start with no price, rows after the expiry date, and
  # rows for bins that never existed
  df <- df %>% na.omit() %>%
    filter(
      date <= expiry_date
    )
  
  return(df)
}

#' Clean daily data by filtering and adjusting price bins
#'
#' Filters to 6 months before contract expiry, computes next higher strike bin,
#' and enforces non-decreasing adjusted prices across strikes (per contract and date).
#'
#' @param df A data frame with columns: date, expiry_date, contract_preamble, strike, yes_price, daily_volume.
#' @return A cleaned data frame with bin_high and adjusted_yes_price columns added.
clean_data <- function(df) {
  
  # remove all observations further than 6 months before contract expiry
  # df <- df %>% mutate(will_remove = (date >= expiry_date - months(6)))
  # filter(
  #   date >= expiry_date - months(6),
  # ) %>%
  # arrange(contract_preamble, strike, date)
  
  
  df <- df %>% arrange(contract_preamble, strike, date)
  
  # sometimes there are clear pricing errors in Kalshi contracts--
  # a strike that is both cheaper and covers the occurence of another contract
  # In this case, we assume that the strictly worse contract actually has an
  # adjusted price equal to the contract that dominates it
  # In other words, we impose monotonic increasing yes_prices
  # from high (least likely to occur) to low (most likely to occur) strikes
  df <- df %>%
    group_by(contract_preamble, date) %>%
    arrange(desc(strike), .by_group = TRUE) %>%
    mutate(
      adjusted_yes_price = cummax(yes_price), 
    ) %>%
    ungroup()
  
  return(df)
  
}

#' Convert adjusted prices to probability distributions
#'
#' Adds low-end bins to each contract/date slice, computes approximate probability
#' buckets by differencing adjusted prices, and iteratively swaps probabilities
#' to smooth out local inconsistencies.
#'
#' @param df A data frame with columns: contract_preamble, date, expiry_date, strike, adjusted_yes_price.
#' @param strike_int A value representing the difference between strikes (how low to set the low bin)
#' @param days_before_horizon A value for removing data too far away from the horizon from the dataset
#' @return A data frame with an added `probability` column representing
#'         approximate probability mass for each strike bin.
convert_to_probabilities <- function(df, strike_int, days_before_horizon) {
  
  # Add low bins representing if even the minimum strike listed was not cleared
  # In order to not skew moments towards 0, the low bin is marked as the
  # strike_int away from the lowest bin listed by Kalshi
  all_cols <- names(df)
  new_rows <- df %>%
    group_by(contract_preamble, date, expiry_date) %>%
    summarise(strike = min(strike) - strike_int, .groups = "drop")
  
  df <- bind_rows(df, new_rows)
  
  # Now, we calculate probabilities by taking 99 (the highest possible yes_price)
  # on Kalshi and subtracting the left-most yes-price. 
  # ie the lowest bin will be: 99 - [price to buy an 'above lowest bin' contract]
  # second lowest bin will be:
  # [price to buy an 'above lowest bin' contract] - [price to buy an 'above 2nd lowest bin' contract]
  # etc...
  df <- df %>% group_by(contract_preamble, date) %>% arrange(strike) %>%
    mutate(probability = 
             ifelse(is.na(lag(strike)), 99.5 - lead(adjusted_yes_price), 
                    # lag(adjusted_yes_price) - adjusted_yes_price
                    ifelse(!is.na(lead(strike)), adjusted_yes_price - lead(adjusted_yes_price), adjusted_yes_price - .5)
             ))
  
  # Remove the days where no trades cause 100 percent probabilities
  # df <- df %>% group_by(contract_preamble, date) %>%
  #   filter(!any(probability == 98)) %>%
  #   ungroup()
  
  # Make sure our probabilities add up to 100
  df <- df %>% group_by(contract_preamble, date) %>% arrange(strike) %>%
    mutate(sum = sum(probability),
           probability = probability * 100 / sum) %>% select(-sum)
  
  df <- df %>% filter(date  >= expiry_date - days(days_before_horizon))
  
  return(df)
  
  
}


# ------------------------
# Compute distribution moments
# ------------------------
weightedGMSkew <- function(x, w, na.rm = TRUE) {
  if (na.rm) {
    sel <- !is.na(x) & !is.na(w)
    x <- x[sel]; w <- w[sel]
  }
  w <- w / sum(w)
  mu <- sum(w * x)
  ord <- order(x); x_o <- x[ord]; w_o <- w[ord]
  cumw <- cumsum(w_o)
  m_w <- x_o[min(which(cumw >= 0.5))]
  mad <- sum(w * abs(x - m_w))
  (mu - m_w) / mad
}

get_moments <- function(df) {
  df %>%
    group_by(date, contract_preamble, expiry_date) %>%
    summarise(
      mean = weighted.mean(strike, probability, na.rm = TRUE),
      median = weightedMedian(strike, w = probability, na.rm = TRUE),
      mode = fmode(strike, w = probability, na.rm = TRUE, ties='first'),
      variance = weightedVar(strike, w = probability, na.rm = TRUE),
      skewness = weightedGMSkew(strike, w = probability, na.rm = TRUE),
      kurtosis = DescTools::Kurt(strike, w = probability, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    na.omit()
}


#' Extract probability distributions and compute moments from raw Kalshi trade data
#'
#' Reads raw data, processes it through several cleaning and transformation steps,
#' computes probability distributions and statistical moments, and writes results to CSV files.
#'
#' @param input_file Path to the input CSV file with raw trade-level data.
#' @param output_distributions Path to output CSV file for the processed probability distributions.
#' @param output_moments Path to output CSV file for the computed moments
#' @param days_before_horizon A value for removing data too far away from the horizon from the dataset
#' @return No return value. Writes processed data to specified output files.
extract_distributions <- function(input_file, output_distributions, output_moments, strike_int,
                                  days_before_horizon) {
  
  df <- read_bid_ask(input_file = input_file)
  df <- fill_dataless_days(df)
  df <- clean_data(df)
  df <- convert_to_probabilities(df, strike_int = strike_int, days_before_horizon)
  moments_df <- get_moments(df)
  
  write_csv(moments_df, output_moments)
  write_csv(df, output_distributions)
}



# ------------------------
# Example calls
# ------------------------
extract_distributions(input_file = 'data/orderbook_data/daily_bid_ask_cpi_data.csv',
                      output_distributions = 'data/daily_bid_ask_distribution_data/daily_distributions_headline_cpi_releases.csv',
                      output_moments = 'data/daily_bid_ask_moments_data/daily_moments_headline_cpi_releases.csv',
                      strike_int = 0.1,
                      days_before_horizon = 30)

extract_distributions(input_file = 'data/orderbook_data/daily_bid_ask_unemployment_data.csv',
                      output_distributions = 'data/daily_bid_ask_distribution_data/daily_distributions_unemployment_releases.csv',
                      output_moments = 'data/daily_bid_ask_moments_data/daily_moments_headline_unemployment_releases.csv',
                      strike_int = 0.1,
                      days_before_horizon = 30)

extract_distributions(input_file = 'data/orderbook_data/daily_bid_ask_fed_decisions_data.csv',
                      output_distributions = 'data/daily_bid_ask_distribution_data/daily_distributions_fed_decisions.csv',
                      output_moments = 'data/daily_bid_ask_moments_data/daily_moments_headline_fed_decisions.csv',
                      strike_int = 0.1,
                      days_before_horizon = 180)
