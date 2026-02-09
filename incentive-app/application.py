from app import create_app

app = create_app()
application = app  # Elastic Beanstalk expects "application"

if __name__ == "__main__":
    app.run(debug=True)