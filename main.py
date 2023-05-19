from flask import Flask, request

app = Flask(__name__)
import ssl

#context = ssl.SSLContext()
#context.load_cert_chain('cert.pem', 'key.pem')
from urllib.parse import urlparse
import re
import requests
from settings import api_keys

import cohere


asin_reg = "(?:[/dp/]|$)([A-Z0-9]{10})"
REVIEWS_MAX_PAGES = 1
MAX_TOKENS_RESPONSE = 3000
@app.route("/")
def hello_world():
    return "<p>Hello, World! - SummarizeX</p>"

@app.route("/summarize", methods = ['POST'])
def summarize():
    url = request.json['url']
    res = summarize_handler(request.json)
    res['url'] = url

    return res

@app.route("/generative_summary", methods = ['POST'])
def generative_summary():
    url = request.json['url']
    res = generate_summary_handler(request.json)
    res['url'] = url

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

    if '.sa' in res['domain']:
        reviews = reviews_api_wrapper(domain, asin, {'language': 'ar_SA'})
    else :
        reviews = reviews_api_wrapper(domain, asin)
        print("REVIEWS ------------------ ")
        print(reviews)
        res['generative'] = run_cohere_generative_summary(reviews)

    return res


def summarize_handler(request) :
    url = request['url']
    res = {}
    get_domain_and_asin(url, res)

    if 'error' in res.keys():
        return res

    domain = res['domain']
    asin = res['asin']

    #call reviews api
    if '.sa' in domain:
        reviews = reviews_api_wrapper(domain, asin, {'language': 'ar_SA'})
    else :
        reviews = reviews_api_wrapper(domain, asin)
        res['summary'] = run_cohere_summarization(reviews)

    return res

def run_arabic_summarization(reviews) :
    API_URL = "https://api-inference.huggingface.co/models/malmarjeh/t5-arabic-text-summarization"
    headers = {"Authorization": f"Bearer {api_keys['huggingface_arabic_bearer']}"}
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()

def run_cohere_summarization(reviews) :
    client = cohere.Client(api_keys['cohere'])
    text = "\n".join(reviews)
    summary = client.summarize(text, additional_command="focusing on how customers felt about the product and the advantages and disadvantages of the product")
    return summary.summary

def run_cohere_generative_summary(reviews) :
    text = ""
    sz = 0
    for r in reviews:
        if sz + len(r) < 2000:
            text += "\n" + r
            sz += len(r)


    prompt = f"Each new line contains a product review from a customer. At the end a summary of the overall sentiment towards the product, the main advantages and disadvantages of the product, the main qualitative descriptors used for the product, will be written:" \
             f"{text}  " \
             f" In summary: "
    client = cohere.Client(api_keys['cohere'])
    print("PROMPT -----------------")
    print(prompt)
    summary = client.generate(prompt, max_tokens=MAX_TOKENS_RESPONSE)
    return summary.generations[-1].text

def reviews_api_wrapper(domain, asin, options={}) :
    params = {
        'api_key': api_keys['amazon_reviews'],
        'amazon_domain': domain,
        'asin': asin,
        'type': 'reviews',
        'output': 'json',
        'max_page': REVIEWS_MAX_PAGES,
        **options
    }
    print("params = ", params)

    # make the http GET request to ASIN Data API
    api_result = requests.get('https://api.asindataapi.com/request', params)
    res_json = api_result.json()
    #extract reviews only
    reviews = [x['body'] for x in res_json['reviews']]
    return reviews


def test_sum():
    url = 'https://www.amazon.com/Lasko-U35115-Electric-Oscillating-Velocity/dp/B081HDGZML?ref_=Oct_DLandingS_D_e95f1a2b_2&th=1'
    res = summarize_handler(url)
    print(res)

if __name__ == "__main__":
    #app.run(ssl_context=context)
    app.run()
    #test_sum()