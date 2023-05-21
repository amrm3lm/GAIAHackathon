from flask import Flask, request, Response

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
from dbm_api import dbm_get_reviews, dbm_put_reviews
import openai

openai.api_key = api_keys['openAI']

asin_reg = "(?:[/dp/]|$)([A-Z0-9]{10})"
REVIEWS_MAX_PAGES = 1
MAX_TOKENS_RESPONSE = 6000
MAX_WORDS_IN_PROMPT = 1200

client = cohere.Client(api_keys['cohere'])

def fix_request_before_handling(request):
    if 'force_review_request' not in request:
        request['force_review_request'] = False

@app.route("/")
def hello_world():
    print("received / request")

    return "<p>Hello, World! - SummarizeX</p>"

@app.route("/summarize", methods = ['POST'])
def summarize():
    print("received summarize request")

    url = request.json['url']
    fix_request_before_handling(request.json)

    res = summarize_handler(request.json)
    res['url'] = url
    code = res['error'] if 'error' in res else 200
    res['summary'] = res['summary'] if code == 200 else res['error_msg']
    return res, code

@app.route("/summarize_ex", methods = ['POST'])
def summarize():
    print("received summarize_ex request")

    url = request.json['url']
    fix_request_before_handling(request.json)

    res = summarize_ex_handler(request.json)
    res['url'] = url
    code = res['error'] if 'error' in res else 200
    res['summary'] = res['summary'] if code == 200 else res['error_msg']
    return res, code

@app.route("/generative_summary", methods = ['POST'])
def generative_summary():
    print("received generative_summary request")

    url = request.json['url']
    fix_request_before_handling(request.json)

    res = generate_summary_handler(request.json)
    res['url'] = url
    code = res['error'] if 'error' in res else 200
    return res, code

@app.route("/query_ex", methods = ['POST'])
def generative_query():
    print("received query request")
    url = request.json['url']

    fix_request_before_handling(request.json)

    res = answer_query_ex_handler(request.json)
    res['url'] = url
    code = res['error'] if 'error' in res else 200
    res['answer'] = res['answer'] if code == 200 else res['error_msg']

    return res, code

#expects 'url' and 'query'
@app.route("/query", methods = ['POST'])
def generative_query():
    print("received query request")
    url = request.json['url']

    fix_request_before_handling(request.json)

    res = answer_query_handler(request.json)
    res['url'] = url
    code = res['error'] if 'error' in res else 200
    res['answer'] = res['answer'] if code == 200 else res['error_msg']

    return res, code

def answer_query_ex_handler(request):
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
    lang = 'Arabic' if ('language' in request and request['language'] == 'ar' ) else 'English'
    prompt = f"This program answers the question {request['query']} in depth based on information in the following sentences" \
             f"{text}" \
             f"Respond in {lang}. the answer to the question {request['query']} is: "

    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.2,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    res['answer'] = response['choices'][0]['text']
    print("answer :", res['answer'])
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
    lang = 'Arabic' if 'sa' in domain else 'English'
    prompt = f"This program answers the question {request['query']} in depth based on information in the following sentences" \
             f"{text}" \
             f"Respond in {lang}. the answer to the question {request['query']} is: "

    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.2,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    res['answer'] = response['choices'][0]['text']
    print("answer :", res['answer'])
    return res

def get_domain_and_asin(url, res):
    #check if its coming from amazon
    domain = urlparse(url).netloc
    if "amazon" not in domain:
        res['error'] = 500
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

def summarize_ex_handler(request) :
    url = request['url']
    res = {}
    get_domain_and_asin(url, res)

    if 'error' in res.keys():
        return res

    domain = res['domain']
    asin = res['asin']

    reviews, votes = dbm_get_reviews(asin)

    #call reviews api
    if 'language' in request and request['language'] == 'ar':
        if reviews == None or request['force_review_request'] == True:

            reviews, votes = reviews_api_wrapper(domain, asin, options={'language': 'ar_SA'})

        res['summary'] = openAI_arabic(reviews)
    else :
        if reviews == None or request['force_review_request'] == True:
            reviews, votes = reviews_api_wrapper(domain, asin)

        res['summary'] = run_cohere_summarization(reviews)

    print("output: ", res['summary'])
    dbm_put_reviews(asin, reviews, votes)

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

        res['summary'] = openAI_arabic(reviews)
    else :
        if reviews == None or request['force_review_request'] == True:
            reviews, votes = reviews_api_wrapper(domain, asin)

        res['summary'] = run_cohere_summarization(reviews)
    print("output: ", res['summary'])
    dbm_put_reviews(asin, reviews, votes)

    return res

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
    summary = client.generate(prompt, max_tokens=MAX_TOKENS_RESPONSE, temperature=0.3)
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

def openAI_arabic(reviews) :

    text = ""
    sz = 0
    for r in reviews:
        if sz + len(r) < MAX_WORDS_IN_PROMPT:
            text += "\n" + r
            sz += len(r)

    text = "\n".join(reviews)
    prompt = "لخصل المراجعات التالية واذكر الانطباع العام تجاه المنتج و ايجابياته و سلبياته" \
    f"{text}" \
    "الملخص: "


    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.2,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    return response['choices'][0]['text']

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

        res['generative'] = run_cohere_generative_summary(reviews)

    print("output: ", res['generative'])
    dbm_put_reviews(asin, reviews,votes)
    return res

def test_sum():
    url = 'https://www.amazon.com/Lasko-U35115-Electric-Oscillating-Velocity/dp/B081HDGZML?ref_=Oct_DLandingS_D_e95f1a2b_2&th=1'
    res = summarize_handler(url)
    print(res)
    print(res.decode("hex").decode("utf8"))


if __name__ == "__main__":
    #app.run(ssl_context=context)
    app.run()
    #test_sum()
