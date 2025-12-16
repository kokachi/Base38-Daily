from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import os
from datetime import datetime
from typing import List, Optional

app = FastAPI()

# --------------------------------------------------
# Supabase setup
# --------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase environment variables not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------
# Models (UNCHANGED)
# --------------------------------------------------

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


class AmbiguousCustomer(BaseModel):
    id: int
    name: str


class AmbiguousCustomerResponse(BaseModel):
    status: str
    reason: str
    mobile_number: str
    customers: List[AmbiguousCustomer]

# --------------------------------------------------
# Customers endpoints (UNCHANGED)
# --------------------------------------------------

@app.get("/customers")
def get_all_customers():
    response = supabase.table("customers").select("*").execute()
    return response.data


@app.get("/customers/{mobile_number}")
def get_customer(mobile_number: str):
    response = (
        supabase
        .table("customers")
        .select("*")
        .eq("mobile_number", mobile_number)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Customer not found")

    return response.data


@app.post("/customers")
def add_customer(customer: Customer):
    response = supabase.table("customers").insert(customer.dict()).execute()

    if not response.data:
        raise HTTPException(
            status_code=400,
            detail="Insert failed. Mobile number may already exist."
        )

    return {"message": "Customer added successfully", "data": response.data}


@app.delete("/customers/{mobile_number}")
def delete_customer(mobile_number: str):
    response = supabase.table("customers").delete().eq("mobile_number", mobile_number).execute()

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.data)

    return {"message": "Customer deleted successfully"}

# --------------------------------------------------
# Visits endpoints (UNCHANGED GETs)
# --------------------------------------------------

@app.get("/visits")
def get_all_visits():
    response = supabase.table("visits").select("*").execute()
    return response.data


@app.get("/visits/{mobile_number}")
def get_visits_by_customer(mobile_number: str):
    response = (
        supabase
        .table("visits")
        .select("*")
        .eq("mobile_number", mobile_number)
        .execute()
    )
    return response.data


@app.delete("/visits/{visit_id}")
def delete_visit(visit_id: str):
    response = supabase.table("visits").delete().eq("id", visit_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Visit not found")

    return {"message": f"Visit {visit_id} deleted successfully"}

# --------------------------------------------------
# POST /visits (EXTENDED but BACKWARD SAFE)
# --------------------------------------------------

@app.post("/visits")
def add_visit(visit: Visit):
    # --------------------------------------------------
    # 1. Insert visit FIRST (original behavior preserved)
    # --------------------------------------------------

    visit_insert = supabase.table("visits").insert(visit.dict()).execute()

    if not visit_insert.data:
        raise HTTPException(status_code=400, detail="Visit insert failed")

    # --------------------------------------------------
    # 2. Calculate visit duration (UNCHANGED)
    # --------------------------------------------------

    fmt = "%H:%M:%S" if len(visit.time_in.split(":")) == 3 else "%H:%M"
    time_in = datetime.strptime(visit.time_in, fmt)
    time_out = datetime.strptime(visit.time_out, fmt)
    duration = (time_out - time_in).seconds / 3600.0

    # --------------------------------------------------
    # 3. Fetch customers by phone (NEW SAFE LOGIC)
    # --------------------------------------------------

    customer_resp = (
        supabase
        .table("customers")
        .select("*")
        .eq("mobile_number", visit.mobile_number)
        .execute()
    )

    customers = customer_resp.data or []

    if len(customers) == 0:
        raise HTTPException(status_code=404, detail="Customer not found")

    if len(customers) > 1:
        return AmbiguousCustomerResponse(
            status="error",
            reason="MULTIPLE_CUSTOMERS_FOR_PHONE",
            mobile_number=visit.mobile_number,
            customers=[
                AmbiguousCustomer(id=c["id"], name=c["name"])
                for c in customers
            ]
        )

    customer = customers[0]

    # --------------------------------------------------
    # 4. Update customer aggregation (UNCHANGED)
    # --------------------------------------------------

    updated_data = {
        "total_money": float(customer["total_money"]) + visit.total_received,
        "total_hours": float(customer["total_hours"]) + duration,
        "visit_count": int(customer["visit_count"]) + 1,
        "last_visit_date": visit.visit_date,
        "last_visit_since": (
            datetime.today().date()
            - datetime.strptime(visit.visit_date, "%Y-%m-%d").date()
        ).days
    }

    update_resp = (
        supabase
        .table("customers")
        .update(updated_data)
        .eq("mobile_number", visit.mobile_number)
        .execute()
    )

    if not update_resp.data:
        raise HTTPException(status_code=400, detail="Customer update failed")

    return {
        "message": "Visit added",
        "mobile_number": visit.mobile_number
    }
