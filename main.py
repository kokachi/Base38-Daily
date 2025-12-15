from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI()

# Load from .env file
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class Visit(BaseModel):
    visit_date: str
    mobile_number: str
    customer_name: str
    people_count: int
    controller_count: int
    time_in: str
    time_out: str
    payment_cash: float
    payment_upi: float
    total_received: float
    discount_applied: str
    loyalty_claimed: float
    loyalty_remaining: float
    total_visits: int
    loyalty_used_to_date: float

class Customer(BaseModel):
    mobile_number: str
    name: str
    total_money: float
    total_hours: float
    visit_count: int
    last_visit_since: int
    last_visit_date: str

# Get all customers
@app.get("/customers")
def get_all_customers():
    response = supabase.table("customers").select("*").execute()
    return response.data

# Get one customer
@app.get("/customers/{mobile_number}")
def get_customer(mobile_number: str):
    response = supabase.table("customers").select("*").eq("mobile_number", mobile_number).single().execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return response.data

# Get all visits
@app.get("/visits")
def get_all_visits():
    response = supabase.table("visits").select("*").execute()
    return response.data

# Get visits by customer mobile number
@app.get("/visits/{mobile_number}")
def get_visits_by_customer(mobile_number: str):
    response = supabase.table("visits").select("*").eq("mobile_number", mobile_number).execute()
    return response.data

@app.post("/visits")
def add_visit(visit: Visit):
    # 1. Insert visit
    response = supabase.table("visits").insert(visit.dict()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Visit insert failed.")

    # 2. Calculate visit duration in hours
    fmt = "%H:%M:%S" if len(visit.time_in.split(":")) == 3 else "%H:%M"
    time_in = datetime.strptime(visit.time_in, fmt)
    time_out = datetime.strptime(visit.time_out, fmt)
    duration = (time_out - time_in).seconds / 3600.0  # hours

    # 3. Fetch existing customer
    customer_resp = supabase.table("customers").select("*").eq("mobile_number", visit.mobile_number).single().execute()
    if not customer_resp.data:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer = customer_resp.data

    # 4. Calculate updated values
    updated_data = {
        "total_money": float(customer["total_money"]) + visit.total_received,
        "total_hours": float(customer["total_hours"]) + duration,
        "visit_count": int(customer["visit_count"]) + 1,
        "last_visit_date": visit.visit_date,
        "last_visit_since": (datetime.today().date() - datetime.strptime(visit.visit_date, "%Y-%m-%d").date()).days
    }

    # 5. Update customer
    update_resp = supabase.table("customers").update(updated_data).eq("mobile_number", visit.mobile_number).execute()
    if not update_resp.data:
        raise HTTPException(status_code=400, detail="Customer update failed")

    return {"message": "Visit added", "mobile_number": visit.mobile_number}

@app.post("/customers")
def add_customer(customer: Customer):
    response = supabase.table("customers").insert(customer.dict()).execute()
    print("SUPABASE RESPONSE:", response)
    if not response.data:
        raise HTTPException(status_code=400, detail="Insert failed. Check if the mobile number already exists or if data is invalid.")

    return {"message": "Customer added successfully", "data": response.data}

# Delete a visit by ID
@app.delete("/visits/{visit_id}")
def delete_visit(visit_id: str):
    response = supabase.table("visits").delete().eq("id", visit_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Visit not found or already deleted")
    return {"message": f"Visit {visit_id} deleted successfully"}

@app.delete("/customers/{mobile_number}")
def delete_customer(mobile_number: str):
    response = supabase.table("customers").delete().eq("mobile_number", mobile_number).execute()
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.data)
    return {"message": "Customer deleted successfully"}
