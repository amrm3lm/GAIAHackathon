from amazon_reviews_scrapper import amazon_product_review_scraper
import requests
import json

print("hello world")

# review_scraper = amazon_product_review_scraper(amazon_site="amazon.com", product_asin="B07X6V2FR3")
# reviews_df = review_scraper.scrape()
# #print(reviews_df)
# print(reviews_df.head(5))

# set up the request parameters
params = {
'api_key': '6642D72A9FBD4911B063B399E3C2939C',
  'amazon_domain': 'amazon.com',
  'asin': 'B0C2VND51M',
  'type': 'product',
  'output': 'json',
  'include_summarization_attributes': 'true'
}

# make the http GET request to ASIN Data API
api_result = requests.get('https://api.asindataapi.com/request', params)

print(api_result)