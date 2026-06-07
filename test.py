from app import create_app

app = create_app()

with app.test_client() as client:
    response = client.get('/static/background.jpg')
    print("Status:", response.status_code)