from flask import Flask , request, jsonify
app = Flask(__name__)
@app.route("/invoice",methods=["POST"])
def recieve_invoice():
    data = request.json
    print(f'Invoice mila : {data}')
    return jsonify({"status": "sucess","message":"invoice recieve ho gya!"})
if __name__ == "__main__":
    app.run(debug=True)

