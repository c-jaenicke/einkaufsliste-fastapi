import os
import uuid
import io
import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from PIL import Image
import pillow_heif

from fastapi import FastAPI, HTTPException, Request, Response, status, File, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg.errors import UniqueViolation

import database
import models
from config import settings

# iPhones default to saving photos as HEIC, which Pillow can't decode
# without this registered as a plugin opener.
pillow_heif.register_heif_opener()

# Limit memory decompression bomb limit to 25 megapixels (e.g. 5000x5000px)
Image.MAX_IMAGE_PIXELS = 25000000

ACCEPTED_IMAGE_CONTENT_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting FastAPI application...")
    try:
        await database.init_db()
    except Exception as e:
        logger.exception("Failed to initialize database during startup")
        raise e
    yield
    # Shutdown
    logger.info("Shutting down FastAPI application...")
    pool = database.get_pool()
    await pool.close()
    logger.info("Database connection pool closed.")

app = FastAPI(lifespan=lifespan)

# Mount static files directory
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Security middleware to prevent MIME-sniffing XSS attacks
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# Setup CORS using loaded configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """
    Lightweight liveness/readiness probe target. Deliberately does not
    touch the database so it can't cascade-fail on transient DB issues.
    """
    return {"status": "ok"}

#
# ITEMS ENDPOINTS
#

@app.get("/items", response_model=List[models.Item])
async def get_items(
    item_status: Optional[str] = Query(None, alias="status"),
    store_id: Optional[int] = None,
    category_id: Optional[int] = None,
    store_name: Optional[str] = None,
    category_name: Optional[str] = None
):
    """
    Get items optionally filtered by status, store, or category.
    Merges and simplifies the old /item/all and /item/specific endpoints.
    """
    try:
        # If no filters are provided, get all items
        if not any([item_status, store_id, category_id, store_name, category_name]):
            return await database.get_all_items()

        return await database.get_items_filtered(
            status=item_status,
            store_id=store_id,
            category_id=category_id,
            store_name=store_name,
            category_name=category_name
        )
    except Exception as e:
        logger.exception("Failed to fetch filtered items")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching items.")

@app.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(item_in: models.ItemCreate):
    """
    Create a new shopping list item.
    """
    try:
        new_id = await database.create_item(
            name=item_in.name,
            note=item_in.note,
            amount=item_in.amount,
            store_id=item_in.store_id,
            category_id=item_in.category_id,
            favorite=item_in.favorite
        )
        return {"status": "created", "id": new_id}
    except Exception as e:
        logger.exception("Failed to create new item")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to create new item.')

@app.get("/items/suggest", response_model=List[str])
async def suggest_items(q: str):
    """
    Get unique item name suggestions matching query 'q', ordered by historical frequency.
    """
    try:
        return await database.suggest_item_names(q)
    except Exception as e:
        logger.exception("Failed to get suggestions")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get suggestions.')

@app.get("/items/frequent", response_model=List[models.FrequentItem])
async def get_frequent_items():
    """
    Get items that are frequently bought/added but not currently active on the list.
    """
    try:
        return await database.get_frequent_items()
    except Exception as e:
        logger.exception("Failed to get frequent items")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get frequent items.')

@app.post("/items/archive")
async def archive_items():
    """
    Clear/archive all items with status = 'bought'.
    """
    try:
        deleted_count = await database.archive_bought_items()
        return {"status": "archived", "deleted_count": deleted_count}
    except Exception as e:
        logger.exception("Failed to archive items")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to archive items.')

@app.get("/items/{id}", response_model=models.Item)
async def get_item(id: int):
    """
    Get a single shopping list item by ID.
    """
    try:
        item = await database.get_item_by_id(id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch item by ID")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to fetch item by ID.')

@app.put("/items/{id}")
async def update_item(id: int, item_in: models.ItemUpdate):
    """
    Update details of an existing shopping list item.
    """
    try:
        # Check if item exists first
        item = await database.get_item_by_id(id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
            
        await database.update_item(
            item_id=id,
            name=item_in.name,
            note=item_in.note,
            amount=item_in.amount,
            store_id=item_in.store_id,
            category_id=item_in.category_id,
            favorite=item_in.favorite
        )
        return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update item")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to update item.')

@app.patch("/items/{id}/status")
async def toggle_item_status(id: int):
    """
    Toggle the status of an item between 'new' and 'bought'.
    """
    try:
        await database.switch_item_status(id)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to switch item status")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to switch item status.')

def delete_local_image(image_path: Optional[str]):
    if image_path:
        relative_path = image_path.lstrip("/")
        if relative_path.startswith(UPLOAD_DIR) and os.path.exists(relative_path):
            try:
                os.remove(relative_path)
            except Exception:
                logger.exception(f"Failed to delete image file: {relative_path}")

@app.delete("/items/{id}")
async def delete_item(id: int):
    """
    Delete a shopping list item by ID.
    """
    try:
        item = await database.get_item_by_id(id)
        if item:
            delete_local_image(item.get("image_path"))
        await database.delete_item(id)
        return {"status": "deleted"}
    except Exception as e:
        logger.exception("Failed to delete item")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to delete item.')

@app.post("/items/{id}/image", response_model=models.Item)
async def upload_item_image(id: int, file: UploadFile = File(...)):
    """
    Upload and sanitize an image for a shopping list item. Re-encodes to WebP and strips metadata.
    """
    item = await database.get_item_by_id(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    if file.content_type not in ACCEPTED_IMAGE_CONTENT_TYPES:
        logger.warning(f"Rejected image upload with content_type={file.content_type!r} filename={file.filename!r}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image format. Use JPEG, PNG, WebP, GIF, or HEIC")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image exceeds 5MB size limit")

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        
        img = Image.open(io.BytesIO(content))
        new_filename = f"{uuid.uuid4().hex}.webp"
        final_path = os.path.join(UPLOAD_DIR, new_filename)
        img.save(final_path, format="WEBP", quality=85)
    except Exception:
        logger.exception("Image processing verification failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or corrupt image file")

    delete_local_image(item.get("image_path"))
    web_path = f"/{UPLOAD_DIR}/{new_filename}"
    updated = await database.update_item_image(id, web_path)
    return updated

@app.delete("/items/{id}/image", response_model=models.Item)
async def delete_item_image(id: int):
    """
    Delete the image associated with a shopping list item.
    """
    item = await database.get_item_by_id(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    delete_local_image(item.get("image_path"))
    updated = await database.update_item_image(id, None)
    return updated

#
# STORES ENDPOINTS
#

@app.get("/stores", response_model=List[models.Store])
async def get_stores():
    """
    Get a list of all stores.
    """
    try:
        return await database.get_all_stores()
    except Exception as e:
        logger.exception("Failed to get stores")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get stores.')

@app.post("/stores", status_code=status.HTTP_201_CREATED)
async def create_store(store_in: models.StoreCreate):
    """
    Create a new store.
    """
    try:
        await database.create_store(name=store_in.name)
        return {"status": "created"}
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A store with this name already exists")
    except Exception as e:
        logger.exception("Failed to create store")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while creating the store.")

@app.put("/stores/{id}")
async def update_store(id: int, store_in: models.StoreUpdate):
    """
    Update a store's name.
    """
    try:
        store_obj = await database.get_store_by_id(id)
        if not store_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        await database.update_store(store_id=id, name=store_in.name)
        return {"status": "updated"}
    except HTTPException:
        raise
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A store with this name already exists")
    except Exception as e:
        logger.exception("Failed to update store")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while updating the store.")

@app.delete("/stores/{id}")
async def delete_store(id: int):
    """
    Delete a store by ID.
    """
    try:
        await database.delete_store(id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete store")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to delete store.')

#
# CATEGORIES ENDPOINTS
#

@app.get("/categories", response_model=List[models.Category])
async def get_categories():
    """
    Get a list of all categories.
    """
    try:
        return await database.get_all_categories()
    except Exception as e:
        logger.exception("Failed to get categories")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get categories.')

@app.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(cat_in: models.CategoryCreate):
    """
    Create a new category.
    """
    try:
        await database.create_category(name=cat_in.name, color=cat_in.color)
        return {"status": "created"}
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A category with this name already exists")
    except Exception as e:
        logger.exception("Failed to create category")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while creating the category.")

@app.put("/categories/{id}")
async def update_category(id: int, cat_in: models.CategoryUpdate):
    """
    Update a category's details (name, color).
    """
    try:
        cat_obj = await database.get_category_by_id(id)
        if not cat_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        await database.update_category(cat_id=id, name=cat_in.name, color=cat_in.color)
        return {"status": "updated"}
    except HTTPException:
        raise
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A category with this name already exists")
    except Exception as e:
        logger.exception("Failed to update category")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while updating the category.")

@app.delete("/categories/{id}")
async def delete_category(id: int):
    """
    Delete a category by ID.
    """
    try:
        await database.delete_category(id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete category")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to delete category.')

#
# PET ENDPOINTS (DB-Persisted, Dynamic & Audited)
#

@app.get("/pet", response_model=models.PetState)
async def get_pet():
    """
    Get the companion pet's status (fallback returning the first pet).
    """
    try:
        pet = await database.get_first_pet()
        if not pet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pets found")
        return pet
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get pet state")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get pet state.')

@app.get("/pets", response_model=List[models.PetState])
async def get_pets():
    """
    Get a list of all companion pets.
    """
    try:
        return await database.get_all_pets()
    except Exception as e:
        logger.exception("Failed to get all pets")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get all pets.')

@app.post("/pets", response_model=models.PetState, status_code=status.HTTP_201_CREATED)
async def create_pet(pet_in: models.PetCreate):
    """
    Create a new companion pet.
    """
    try:
        return await database.create_pet(name=pet_in.name)
    except Exception as e:
        logger.exception("Failed to create new pet")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to create new pet.')

@app.get("/pets/{id}", response_model=models.PetState)
async def get_pet_by_id(id: int):
    """
    Get details of a specific companion pet by ID.
    """
    try:
        pet = await database.get_pet_by_id(id)
        if not pet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
        return pet
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch pet by ID")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to fetch pet by ID.')

@app.put("/pets/{id}", response_model=models.PetState)
async def update_pet(id: int, pet_in: models.PetUpdate):
    """
    Rename a companion pet.
    """
    try:
        updated = await database.update_pet_name(id, name=pet_in.name)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update pet name")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to update pet name.')

@app.delete("/pets/{id}")
async def delete_pet(id: int):
    """
    Remove a companion pet.
    """
    try:
        # Check if pet exists
        pet = await database.get_pet_by_id(id)
        if not pet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
        await database.delete_pet(id)
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete pet")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to delete pet.')

@app.patch("/pets/{id}/location", response_model=models.PetState)
async def toggle_pet_location(id: int):
    """
    Toggle whether a specific pet is inside or outside.
    """
    try:
        return await database.update_pet_location(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to toggle pet location")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to toggle pet location.')

@app.post("/pets/{id}/feed", response_model=models.PetState)
async def feed_pet(id: int, feed_in: models.PetFeed):
    """
    Feed a specific pet a portion amount.
    """
    try:
        return await database.feed_pet(pet_id=id, amount=feed_in.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to feed pet")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to feed pet.')

@app.get("/pets/{id}/logs", response_model=List[models.PetLog])
async def get_pet_logs(id: int):
    """
    Get audit/interaction activity logs for a specific companion pet.
    """
    try:
        # Check if pet exists
        pet = await database.get_pet_by_id(id)
        if not pet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
        return await database.get_pet_logs(id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch pet logs")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to fetch pet logs.')

#
# RECIPES ENDPOINTS
#

@app.get("/recipes", response_model=List[models.Recipe])
async def get_recipes():
    """
    Get a list of all recipes.
    """
    try:
        return await database.get_all_recipes()
    except Exception as e:
        logger.exception("Failed to get recipes")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to get recipes.')

@app.post("/recipes", response_model=models.RecipeDetail, status_code=status.HTTP_201_CREATED)
async def create_recipe(recipe_in: models.RecipeCreate):
    """
    Create a new recipe with all its ingredients.
    """
    try:
        # Convert Pydantic ingredients list to Dict
        ingredients_data = [ing.model_dump() for ing in recipe_in.ingredients]
        return await database.create_recipe(
            name=recipe_in.name,
            description=recipe_in.description,
            ingredients=ingredients_data
        )
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A recipe with this name already exists")
    except Exception as e:
        logger.exception("Failed to create recipe")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while creating the recipe.")

@app.get("/recipes/{id}", response_model=models.RecipeDetail)
async def get_recipe(id: int):
    """
    Get detailed information of a specific recipe, including its ingredient list.
    """
    try:
        recipe = await database.get_recipe_by_id(id)
        if not recipe:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
        recipe["ingredients"] = await database.get_recipe_ingredients(id)
        return recipe
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch recipe detail")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to fetch recipe detail.')

@app.put("/recipes/{id}", response_model=models.RecipeDetail)
async def update_recipe(id: int, recipe_in: models.RecipeUpdate):
    """
    Update a recipe's name, description, and replace its ingredient list.
    """
    try:
        ingredients_data = [ing.model_dump() for ing in recipe_in.ingredients]
        updated = await database.update_recipe(
            recipe_id=id,
            name=recipe_in.name,
            description=recipe_in.description,
            ingredients=ingredients_data
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
        return updated
    except HTTPException:
        raise
    except UniqueViolation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A recipe with this name already exists")
    except Exception as e:
        logger.exception("Failed to update recipe")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while updating the recipe.")

@app.delete("/recipes/{id}")
async def delete_recipe(id: int):
    """
    Delete a recipe and all its ingredients.
    """
    try:
        # Check if exists
        recipe = await database.get_recipe_by_id(id)
        if not recipe:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
        # Clean up local image if exists
        delete_local_image(recipe.get("image_path"))
        await database.delete_recipe(id)
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete recipe")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to delete recipe.')

@app.post("/recipes/{id}/image", response_model=models.RecipeDetail)
async def upload_recipe_image(id: int, file: UploadFile = File(...)):
    """
    Upload and sanitize an image for a recipe. Re-encodes to WebP and strips metadata.
    """
    recipe = await database.get_recipe_by_id(id)
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    if file.content_type not in ACCEPTED_IMAGE_CONTENT_TYPES:
        logger.warning(f"Rejected image upload with content_type={file.content_type!r} filename={file.filename!r}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image format. Use JPEG, PNG, WebP, GIF, or HEIC")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image exceeds 5MB size limit")

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        
        img = Image.open(io.BytesIO(content))
        new_filename = f"{uuid.uuid4().hex}.webp"
        final_path = os.path.join(UPLOAD_DIR, new_filename)
        img.save(final_path, format="WEBP", quality=85)
    except Exception:
        logger.exception("Image processing verification failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or corrupt image file")

    delete_local_image(recipe.get("image_path"))
    web_path = f"/{UPLOAD_DIR}/{new_filename}"
    updated = await database.update_recipe_image(id, web_path)
    return updated

@app.delete("/recipes/{id}/image", response_model=models.RecipeDetail)
async def delete_recipe_image(id: int):
    """
    Delete the image associated with a recipe.
    """
    recipe = await database.get_recipe_by_id(id)
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    delete_local_image(recipe.get("image_path"))
    updated = await database.update_recipe_image(id, None)
    return updated

@app.post("/recipes/{id}/add")
async def add_recipe_to_list(id: int):
    """
    Add all ingredients of a recipe to the active shopping list with one click, utilizing prediction defaults.
    """
    try:
        recipe = await database.get_recipe_by_id(id)
        if not recipe:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
        added_count = await database.add_recipe_to_shopping_list(id)
        return {"status": "added", "added_count": added_count}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to add recipe to list")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An internal error occurred: failed to add recipe to list.')


@app.get("/meal-plans", response_model=List[models.MealPlanDetail])
async def get_meal_plans():
    """
    Retrieve all meal plan records.
    """
    plans = await database.get_all_meal_plans()
    result = []
    for p in plans:
        recipe_obj = None
        if p["recipe_id"]:
            recipe_obj = models.Recipe(
                id=p["recipe_id"],
                name=p["recipe_name"],
                description=p["recipe_description"] or "",
                image_path=p["recipe_image_path"],
                created_at=p["created_at"],
                updated_at=p["updated_at"]
            )
        result.append(models.MealPlanDetail(
            id=p["id"],
            date=p["date"],
            meal_type=p["meal_type"],
            recipe_id=p["recipe_id"],
            note=p["note"],
            created_at=p["created_at"],
            updated_at=p["updated_at"],
            recipe=recipe_obj
        ))
    return result


@app.post("/meal-plans", response_model=models.MealPlan, status_code=status.HTTP_201_CREATED)
async def create_meal_plan(plan: models.MealPlanCreate):
    """
    Create a new meal plan entry.
    """
    if plan.recipe_id:
        recipe = await database.get_recipe_by_id(plan.recipe_id)
        if not recipe:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    new_plan = await database.create_meal_plan(
        date=plan.date,
        meal_type=plan.meal_type,
        recipe_id=plan.recipe_id,
        note=plan.note
    )
    return new_plan


@app.delete("/meal-plans/{id}")
async def delete_meal_plan(id: int):
    """
    Delete a meal plan entry by ID.
    """
    plan = await database.get_meal_plan_by_id(id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal plan not found")
    await database.delete_meal_plan(id)
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
