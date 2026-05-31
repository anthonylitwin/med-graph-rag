import mlflow


def main() -> None:
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("medgraphrag-local")

    with mlflow.start_run(run_name="dummy-baseline"):
        mlflow.log_param("model_type", "mock-baseline")
        mlflow.log_param("fine_tuned", False)
        mlflow.log_metric("accuracy", 0.0)
        mlflow.log_metric("graph_recall", 0.0)

    print("Logged dummy MLflow run.")


if __name__ == "__main__":
    main()