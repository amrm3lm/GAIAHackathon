from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, World! - SummarizeX</p>"

@app.route("/summarize", methods = ['POST'])
def summarize():
    url = request.form.get('url')
    res = {}
    res['url'] = url
    res['response'] = "very very good product!"
    return res