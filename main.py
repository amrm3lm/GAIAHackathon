from flask import Flask, request

app = Flask(__name__)
import ssl
import dbm
#context = ssl.SSLContext()
#context.load_cert_chain('cert.pem', 'key.pem')
from urllib.parse import urlparse
import re
import requests
from settings import api_keys
from langdetect import detect

import cohere
from bert_arabic import run_arabic_summary
from dbm_api import  dbm_clean, dbm_get, dbm_put, dbm_get_reviews, dbm_put_reviews

asin_reg = "(?:[/dp/]|$)([A-Z0-9]{10})"
REVIEWS_MAX_PAGES = 1
MAX_TOKENS_RESPONSE = 3000
MAX_WORDS_IN_PROMPT = 1000

client = cohere.Client(api_keys['cohere'])

def fix_request_before_handling(request):
    if 'force_review_request' not in request:
        request['force_review_request'] = False

@app.route("/")
def hello_world():
    return "<p>Hello, World! - SummarizeX</p>"

@app.route("/summarize", methods = ['POST'])
def summarize():
    url = request.json['url']
    fix_request_before_handling(request.json)

    res = summarize_handler(request.json)
    res['url'] = url

    return res

@app.route("/generative_summary", methods = ['POST'])
def generative_summary():
    url = request.json['url']
    fix_request_before_handling(request.json)

    res = generate_summary_handler(request.json)
    res['url'] = url

    return res

#expects 'url' and 'query'
@app.route("/query", methods = ['POST'])
def generative_query():
    url = request.json['url']

    fix_request_before_handling(request.json)

    res = answer_query_handler(request.json)
    res['url'] = url

    return res

def answer_query_handler(request):
    url = request['url']
    res = {}
    get_domain_and_asin(url, res)
    domain = res['domain']
    asin = res['asin']

    print("asin = ", asin)
    reviews, votes = dbm_get_reviews(asin)
    print("reviews = ", reviews)

    if reviews == None or request['force_review_request'] == True:
        reviews, votes = reviews_api_wrapper(domain, asin)

    response = client.rerank(
        model='rerank-english-v2.0',
        query=request['query'],
        documents=reviews,
        top_n=20,
    )
    print("ranked res ", response)

    used_reviews = []
    sz = 0
    for r in response.results:
        i = r.index
        used_reviews.append(reviews[i])
        sz += len(reviews[i])

        if sz > MAX_WORDS_IN_PROMPT:
            break
    text = "\n".join(used_reviews)

    prompt = f"This program answers the question {request['query']} in depth and using multiple perspectives based on information in the following sentences" \
             f"{text}" \
             f"the answer to the question {request['query']} is: "

    res['answer'] = client.generate(prompt, max_tokens=MAX_TOKENS_RESPONSE).generations[0].text
    return res


def get_domain_and_asin(url, res):
    #check if its coming from amazon
    domain = urlparse(url).netloc
    if "amazon" not in domain:
        res['error'] = 400
        res['error_msg'] = "not amazon domain"
        return res

    first = domain.find("amazon")
    domain = domain[first:]
    #extracting asin
    #https://www.amazon.com/Lasko-U35115-Electric-Oscillating-Velocity/dp/B081HDGZML?ref_=Oct_DLandingS_D_e95f1a2b_2&th=1
    #m = re.match(asin_reg, url)
    m = re.search(r'/[dg]p/([^/]+)', url, flags=re.IGNORECASE)
    word = m.group(1)
    if word is not None:
        if word[0]== '/':
            asin = word[1:11]
        else:
            asin = word[:10]
    else:
        res['error'] = 404
        res['error_msg'] = "ASIN could not be extracted"
        return res

    print(f"found asin {asin} and domain {domain}")
    res['asin'] = asin
    res['domain'] = domain

def generate_summary_handler(request):
    url = request['url']
    res = {}
    get_domain_and_asin(url, res)

    if 'error' in res.keys():
        return res

    domain = res['domain']
    asin = res['asin']

    reviews, votes = dbm_get_reviews(asin)

    if '.sa' in res['domain']:
        if reviews == None:
            reviews, votes = reviews_api_wrapper(domain, asin, options={'language': 'ar_SA'})
        else:
            print("using cache")
    else :
        if reviews == None:
            reviews, votes = reviews_api_wrapper(domain, asin)

        print("REVIEWS ------------------ ")
        print(reviews)
        res['generative'] = run_cohere_generative_summary(reviews)

    dbm_put_reviews(asin, reviews,votes)
    return res


def summarize_handler(request) :
    url = request['url']
    res = {}
    get_domain_and_asin(url, res)

    if 'error' in res.keys():
        return res

    domain = res['domain']
    asin = res['asin']

    reviews, votes = dbm_get_reviews(asin)

    #call reviews api
    if '.sa' in domain:
        if reviews == None or request['force_review_request'] == True:

            reviews, votes = reviews_api_wrapper(domain, asin, options={'language': 'ar_SA'})

            #filter out non arabic
            for r,v in zip(reviews, votes):
                if detect(r) != 'ar':
                    i = reviews.index(r)
                    reviews.pop(i)
                    votes.pop(i)

            print("reviews - should be only arabic: ")
            print(reviews)

        for i in reviews:
            print(i)
        res['summary'] = run_arabic_summary(reviews[1:])
    else :
        if reviews == None or request['force_review_request'] == True:
            reviews, votes = reviews_api_wrapper(domain, asin)

        res['summary'] = run_cohere_summarization(reviews)
    dbm_put_reviews(asin, reviews, votes)

    return res

def run_arabic_summarization(reviews) :
    summary = run_arabic_summary(reviews)
    return summary

def run_cohere_summarization(reviews) :
    text = "\n".join(reviews)
    summary = client.summarize(text, additional_command="focusing on how customers felt about the product and the advantages and disadvantages of the product")
    return summary.summary

def run_cohere_generative_summary(reviews) :
    text = ""
    sz = 0
    for r in reviews:
        if sz + len(r) < MAX_WORDS_IN_PROMPT:
            text += "\n" + r
            sz += len(r)


    prompt = f"Each new line contains a product review from a customer. At the end a summary of the overall sentiment towards the product, the main advantages and disadvantages of the product, the main qualitative descriptors used for the product, will be written:" \
             f"{text}  " \
             f" In summary: "
    print("PROMPT -----------------")
    print(prompt)
    summary = client.generate(prompt, max_tokens=MAX_TOKENS_RESPONSE)
    return summary.generations[-1].text


def reviews_api_wrapper(domain, asin, num_pages=1, options={}):
    params = {
        'api_key': api_keys['amazon_reviews_rainforrestapi'],
        'amazon_domain': domain,
        'asin': asin,
        'type': 'reviews',
        'output': 'json',
        'page': 1,
        **options
    }

    total_reviews = []
    total_votes = []

    for i in range(1, num_pages + 1):
        params['page'] = i
        print("params = ", params)

        # make the http GET request to ASIN Data API
        api_result = requests.get('https://api.rainforestapi.com/request', params)
        res_json = api_result.json()
        #print(res_json)
        #print("----------------------------------------------------")
        # extract reviews only
        reviews = []
        helpful_votes = []
        for x in res_json['reviews']:
            reviews.append(x['body'])
            if 'helpful_votes' in x.keys():
                helpful_votes.append(x['helpful_votes'])
            else:
                helpful_votes.append(0)

        total_reviews.extend(reviews)
        total_votes.extend(helpful_votes)

        total_pages = res_json['pagination']['total_pages']

        if i == total_pages:
            break
    print(f"returned a total of {len(total_reviews)} reviews")
    return total_reviews, total_votes


def test_sum():
    url = 'https://www.amazon.com/Lasko-U35115-Electric-Oscillating-Velocity/dp/B081HDGZML?ref_=Oct_DLandingS_D_e95f1a2b_2&th=1'
    res = summarize_handler(url)
    print(res)

if __name__ == "__main__":
    #app.run(ssl_context=context)
    app.run()
    #test_sum()