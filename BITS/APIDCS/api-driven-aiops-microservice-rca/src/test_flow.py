from prefect import flow, task


@task
def say_hello():
    print("Hello from Prefect task!")


@flow
def first_test_flow():
    print("Starting Prefect flow...")
    say_hello()
    print("Flow completed successfully.")


if __name__ == "__main__":
    first_test_flow()