from abc import ABC, abstractmethod

from src.pipline.prediction_pipeline import VehicleData, VehicleDataClassifier
from src.pipline.training_pipeline import TrainPipeline

from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from uvicorn import run as app_run

from typing import Any, Optional

# Importing constants and pipeline modules from the project
from src.constants import APP_HOST, APP_PORT
from src.pipline.prediction_pipeline import VehicleData, VehicleDataClassifier
from src.pipline.training_pipeline import TrainPipeline

class BaseApp(ABC):
    """Application lifecycle contract for the API app."""

    @abstractmethod
    def configure_cors(self) -> None:
        """Configure CORS policy for the app."""

    @abstractmethod
    def mount_static_assets(self) -> None:
        """Mount frontend static assets for the app."""

    @abstractmethod
    def configure_templates(self) -> None:
        """Configure the Jinja2 template engine for rendering HTML pages."""


class App(FastAPI, BaseApp):
    """Concrete FastAPI application that configures its required services."""

    def __init__(self):
        super().__init__()
        self.configure_cors()
        self.mount_static_assets()
        self.configure_templates()

    def configure_cors(self) -> None:
        origins = ["*"]
        self.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def mount_static_assets(self) -> None:
        self.mount("/static", StaticFiles(directory="static"), name="static")

    def configure_templates(self) -> None:
        self.templates = Jinja2Templates(directory="templates")


# Initialize FastAPI application
app = App()

# Set up Jinja2 template engine for rendering HTML templates
templates = app.templates

class DataForm:
    """
    DataForm class to handle and process incoming form data.
    This class defines the vehicle-related attributes expected from the form.
    """
    def __init__(self, request: Request):
        self.request: Request = request
        self.Gender: Optional[int] = None
        self.Age: Optional[int] = None
        self.Driving_License: Optional[int] = None
        self.Region_Code: Optional[float] = None
        self.Previously_Insured: Optional[int] = None
        self.Annual_Premium: Optional[float] = None
        self.Policy_Sales_Channel: Optional[float] = None
        self.Vintage: Optional[int] = None
        self.Vehicle_Age_lt_1_Year: Optional[int] = None
        self.Vehicle_Age_gt_2_Years: Optional[int] = None
        self.Vehicle_Damage_Yes: Optional[int] = None

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        return None

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        return None

    async def get_vehicle_data(self):
        """
        Method to retrieve and assign form data to class attributes.
        This method is asynchronous to handle form data fetching without blocking.
        """
        form = await self.request.form()
        self.Gender = self._to_int(form.get("Gender"))
        self.Age = self._to_int(form.get("Age"))
        self.Driving_License = self._to_int(form.get("Driving_License"))
        self.Region_Code = self._to_float(form.get("Region_Code"))
        self.Previously_Insured = self._to_int(form.get("Previously_Insured"))
        self.Annual_Premium = self._to_float(form.get("Annual_Premium"))
        self.Policy_Sales_Channel = self._to_float(form.get("Policy_Sales_Channel"))
        self.Vintage = self._to_int(form.get("Vintage"))
        self.Vehicle_Age_lt_1_Year = self._to_int(form.get("Vehicle_Age_lt_1_Year"))
        self.Vehicle_Age_gt_2_Years = self._to_int(form.get("Vehicle_Age_gt_2_Years"))
        self.Vehicle_Damage_Yes = self._to_int(form.get("Vehicle_Damage_Yes"))


def _normalize_prediction_value(value: object) -> int:
    """Convert a model prediction into a safe integer 0/1 value."""
    current: Any = value

    iloc_accessor = getattr(current, "iloc", None)
    if iloc_accessor is not None:
        current = iloc_accessor[0]

    if isinstance(current, (list, tuple)) and len(current) > 0:
        current = current[0]

    iloc_accessor = getattr(current, "iloc", None)
    if iloc_accessor is not None:
        current = iloc_accessor[0]

    item_fn = getattr(current, "item", None)
    if callable(item_fn):
        try:
            current = item_fn()
        except (AttributeError, ValueError, TypeError):
            pass

    if isinstance(current, str):
        try:
            return int(float(current))
        except ValueError:
            return 0
    if isinstance(current, (int, float)):
        return int(current)
    return 0

# Route to render the main page with the form
@app.get("/", tags=["authentication"])
async def index(request: Request):
    """
    Renders the main HTML form page for vehicle data input.
    """
    return templates.TemplateResponse(
        request,
        "vehicledata.html",
        {"request": request, "context": "Rendering"},
    )

# Route to trigger the model training process
@app.get("/train")
async def trainRouteClient():
    """
    Endpoint to initiate the model training pipeline.
    """
    try:
        train_pipeline = TrainPipeline()
        train_pipeline.run_pipeline()
        return Response("Training successful!!!")

    except Exception as e:
        return Response(f"Error Occurred! {e}")

# Route to handle form submission and make predictions
@app.post("/")
async def predictRouteClient(request: Request):
    """
    Endpoint to receive form data, process it, and make a prediction.
    """
    try:
        form = DataForm(request)
        await form.get_vehicle_data()
        
        vehicle_data = VehicleData(
                                Gender= form.Gender,
                                Age = form.Age,
                                Driving_License = form.Driving_License,
                                Region_Code = form.Region_Code,
                                Previously_Insured = form.Previously_Insured,
                                Annual_Premium = form.Annual_Premium,
                                Policy_Sales_Channel = form.Policy_Sales_Channel,
                                Vintage = form.Vintage,
                                Vehicle_Age_lt_1_Year = form.Vehicle_Age_lt_1_Year,
                                Vehicle_Age_gt_2_Years = form.Vehicle_Age_gt_2_Years,
                                Vehicle_Damage_Yes = form.Vehicle_Damage_Yes
                                )

        # Convert form data into a DataFrame for the model
        vehicle_df = vehicle_data.get_vehicle_input_data_frame()

        # Initialize the prediction pipeline
        model_predictor = VehicleDataClassifier()

        # Make a prediction and retrieve the result
        prediction = model_predictor.predict(dataframe=vehicle_df)
        normalized_value = _normalize_prediction_value(prediction)

        # Interpret the prediction result as 'Response-Yes' or 'Response-No'
        status = "Response-Yes" if normalized_value == 1 else "Response-No"

        # Render the same HTML page with the prediction result
        return templates.TemplateResponse(
            request,
            "vehicledata.html",
            {"request": request, "context": status},
        )
        
    except Exception as e:
        return {"status": False, "error": f"{e}"}

# Main entry point to start the FastAPI server
if __name__ == "__main__":
    app_run(app, host=APP_HOST, port=APP_PORT)