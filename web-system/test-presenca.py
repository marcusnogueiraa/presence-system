import requests

url = "http://localhost:5000/api/registrar_presenca"
dados = {
    "rfid": "UY IU NK SD",
    "uuid": "8cb253dd-ea4a-4f37-b5dd-60e5d1e1c526" # UUID da turma
}

response = requests.post(url, json=dados)
print(response.json())