import re
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict

HEX_COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')

#
# CATEGORY MODELS
#
class CategoryBase(BaseModel):
    name: str
    color: str

class CategoryCreate(CategoryBase):
    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("color")
    @classmethod
    def check_hex_color(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        v_clean = v.strip()
        if not HEX_COLOR_RE.match(v_clean):
            raise ValueError("must be a valid hex color code (e.g., #ffffff or #abc)")
        return v_clean

class CategoryUpdate(CategoryCreate):
    pass

class Category(CategoryBase):
    id: int
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

#
# STORE MODELS
#
class StoreBase(BaseModel):
    name: str

class StoreCreate(StoreBase):
    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

class StoreUpdate(StoreCreate):
    pass

class Store(StoreBase):
    id: int
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

#
# ITEM MODELS
#
class ItemBase(BaseModel):
    name: str
    note: str = ""
    amount: int
    store_id: Optional[int] = None
    category_id: Optional[int] = None

class ItemCreate(ItemBase):
    @field_validator("name")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def check_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

class ItemUpdate(ItemCreate):
    pass

class Item(ItemBase):
    id: int
    status: str = "new"
    image_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FrequentItem(BaseModel):
    name: str
    store_id: Optional[int] = None
    category_id: Optional[int] = None
    purchase_count: int

    model_config = ConfigDict(from_attributes=True)

#
# PET MODELS
#
class PetCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

class PetUpdate(PetCreate):
    pass

class PetState(BaseModel):
    id: int
    name: str
    fed_at: int
    amount_fed: str = ""
    is_inside: bool = False
    inside_at: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PetFeed(BaseModel):
    amount: str

    @field_validator("amount")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

class PetLog(BaseModel):
    id: int
    pet_id: int
    activity_type: str
    detail: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

#
# RECIPE MODELS
#
class RecipeIngredientBase(BaseModel):
    name: str
    amount: int = 1
    note: str = ""
    store_id: Optional[int] = None
    category_id: Optional[int] = None

    @field_validator("name")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def check_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

class RecipeIngredientCreate(RecipeIngredientBase):
    pass

class RecipeIngredient(RecipeIngredientBase):
    id: int
    recipe_id: int

    model_config = ConfigDict(from_attributes=True)

class RecipeBase(BaseModel):
    name: str
    description: str = ""

class RecipeCreate(RecipeBase):
    ingredients: List[RecipeIngredientBase] = []

    @field_validator("name")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

class RecipeUpdate(RecipeCreate):
    pass

class Recipe(RecipeBase):
    id: int
    image_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RecipeDetail(Recipe):
    ingredients: List[RecipeIngredient] = []


#
# MEAL PLAN MODELS
#
class MealPlanBase(BaseModel):
    date: str  # Format: YYYY-MM-DD
    meal_type: str  # Frühstück, Mittagessen, Abendessen, Snack
    recipe_id: Optional[int] = None
    note: Optional[str] = None

class MealPlanCreate(MealPlanBase):
    @field_validator("date")
    @classmethod
    def check_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError("must be in YYYY-MM-DD format")
        return v

    @field_validator("meal_type")
    @classmethod
    def check_meal_type(cls, v: str) -> str:
        valid = {"Frühstück", "Mittagessen", "Abendessen", "Snack"}
        if v not in valid:
            raise ValueError("must be one of: Frühstück, Mittagessen, Abendessen, Snack")
        return v

class MealPlanUpdate(MealPlanCreate):
    pass

class MealPlan(MealPlanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MealPlanDetail(MealPlan):
    recipe: Optional[Recipe] = None

