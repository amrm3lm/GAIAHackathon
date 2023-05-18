from amazon_reviews_scrapper import amazon_product_review_scraper
print("hello world")

review_scraper = amazon_product_review_scraper(amazon_site="amazon.com", product_asin="B07X6V2FR3")
reviews_df = review_scraper.scrape()
#print(reviews_df)
print(reviews_df.head(5))