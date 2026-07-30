import pytest
from fastapi import status

pytestmark = pytest.mark.asyncio

async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}

#
# CATEGORY ENDPOINT TESTS
#

async def test_get_categories(client):
    response = await client.get("/categories")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "keine"
    assert data[0]["color"] == "#ffffff"
    assert data[0]["id"] == 1

async def test_create_category_validation(client):
    # Empty name should fail
    response = await client.post("/categories", json={"name": "", "color": "#00ff00"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_create_category_success(client):
    response = await client.post("/categories", json={"name": "Groceries", "color": "#00ff00"})
    assert response.status_code == status.HTTP_201_CREATED
    
    # Check that it exists now
    response = await client.get("/categories")
    data = response.json()
    assert len(data) == 2
    names = [c["name"] for c in data]
    assert "Groceries" in names

async def test_update_category(client):
    # First create a category
    await client.post("/categories", json={"name": "Veggies", "color": "#00ff00"})
    
    response = await client.get("/categories")
    veggies = next(c for c in response.json() if c["name"] == "Veggies")
    cat_id = veggies["id"]
    
    # Update it
    response = await client.put(f"/categories/{cat_id}", json={"name": "Vegetables", "color": "#00ee00"})
    assert response.status_code == status.HTTP_200_OK
    
    # Verify updates
    response = await client.get("/categories")
    updated = next(c for c in response.json() if c["id"] == cat_id)
    assert updated["name"] == "Vegetables"
    assert updated["color"] == "#00ee00"

async def test_delete_category(client):
    await client.post("/categories", json={"name": "Meats", "color": "#ff0000"})
    
    response = await client.get("/categories")
    meat = next(c for c in response.json() if c["name"] == "Meats")
    cat_id = meat["id"]
    
    response = await client.delete(f"/categories/{cat_id}")
    assert response.status_code == status.HTTP_200_OK
    
    # Ensure it is gone
    response = await client.get("/categories")
    assert not any(c["id"] == cat_id for c in response.json())

#
# STORE ENDPOINT TESTS
#

async def test_get_stores(client):
    response = await client.get("/stores")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "keiner"
    assert data[0]["id"] == 1

async def test_create_store_validation(client):
    response = await client.post("/stores", json={"name": "  "})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_create_store_success(client):
    response = await client.post("/stores", json={"name": "Supermarket"})
    assert response.status_code == status.HTTP_201_CREATED
    
    response = await client.get("/stores")
    assert any(s["name"] == "Supermarket" for s in response.json())

async def test_update_store(client):
    await client.post("/stores", json={"name": "Lidl"})
    response = await client.get("/stores")
    lidl = next(s for s in response.json() if s["name"] == "Lidl")
    store_id = lidl["id"]
    
    response = await client.put(f"/stores/{store_id}", json={"name": "Lidl Super"})
    assert response.status_code == status.HTTP_200_OK
    
    response = await client.get("/stores")
    updated = next(s for s in response.json() if s["id"] == store_id)
    assert updated["name"] == "Lidl Super"

async def test_delete_store(client):
    await client.post("/stores", json={"name": "Kaufland"})
    response = await client.get("/stores")
    kaufland = next(s for s in response.json() if s["name"] == "Kaufland")
    store_id = kaufland["id"]
    
    response = await client.delete(f"/stores/{store_id}")
    assert response.status_code == status.HTTP_200_OK
    
    response = await client.get("/stores")
    assert not any(s["id"] == store_id for s in response.json())

#
# ITEM ENDPOINT TESTS
#

async def test_create_item_validation(client):
    # Quantity <= 0 should fail
    response = await client.post("/items", json={"name": "Milk", "amount": 0})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Empty name should fail
    response = await client.post("/items", json={"name": "", "amount": 2})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_create_item_success(client):
    response = await client.post("/items", json={"name": "Milk", "amount": 2, "note": "1.5% fat"})
    assert response.status_code == status.HTTP_201_CREATED
    created_id = response.json()["id"]
    assert isinstance(created_id, int)

    response = await client.get("/items")
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Milk"
    assert data[0]["amount"] == 2
    assert data[0]["note"] == "1.5% fat"
    assert data[0]["status"] == "new"
    # Defaults should map to default ID 1 ('keine'/'keiner') if not provided
    assert data[0]["store_id"] == 1
    assert data[0]["category_id"] == 1

async def test_get_item_by_id(client):
    await client.post("/items", json={"name": "Cheese", "amount": 1})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]
    
    response = await client.get(f"/items/{item_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "Cheese"

async def test_get_item_not_found(client):
    response = await client.get("/items/99999")
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_update_item(client):
    # Create item
    await client.post("/items", json={"name": "Butter", "amount": 1})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]

    # Update item
    response = await client.put(f"/items/{item_id}", json={
        "name": "Salted Butter",
        "note": "Bio",
        "amount": 3,
        "store_id": 1,
        "category_id": 1,
        "favorite": True
    })
    assert response.status_code == status.HTTP_200_OK

    # Verify details
    response = await client.get(f"/items/{item_id}")
    data = response.json()
    assert data["name"] == "Salted Butter"
    assert data["note"] == "Bio"
    assert data["amount"] == 3
    assert data["store_id"] == 1
    assert data["category_id"] == 1
    assert data["favorite"] is True

async def test_toggle_item_status(client):
    await client.post("/items", json={"name": "Eggs", "amount": 10})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]
    
    # Toggle 'new' -> 'bought'
    response = await client.patch(f"/items/{item_id}/status")
    assert response.status_code == status.HTTP_200_OK
    
    response = await client.get(f"/items/{item_id}")
    assert response.json()["status"] == "bought"
    
    # Toggle 'bought' -> 'new'
    response = await client.patch(f"/items/{item_id}/status")
    assert response.status_code == status.HTTP_200_OK
    
    response = await client.get(f"/items/{item_id}")
    assert response.json()["status"] == "new"

async def test_create_item_favorite(client):
    response = await client.post("/items", json={"name": "Eggs", "amount": 10, "favorite": True})
    assert response.status_code == status.HTTP_201_CREATED

    response = await client.get("/items")
    assert response.json()[0]["favorite"] is True

async def test_delete_item(client):
    await client.post("/items", json={"name": "Bread", "amount": 1})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]
    
    response = await client.delete(f"/items/{item_id}")
    assert response.status_code == status.HTTP_200_OK
    
    response = await client.get("/items")
    assert len(response.json()) == 0

async def test_item_filtering(client):
    # Setup test store & category
    await client.post("/stores", json={"name": "Rewe"})
    response = await client.get("/stores")
    rewe_id = next(s["id"] for s in response.json() if s["name"] == "Rewe")
    
    await client.post("/categories", json={"name": "Bakery", "color": "#773300"})
    response = await client.get("/categories")
    bakery_id = next(c["id"] for c in response.json() if c["name"] == "Bakery")
    
    # Create multiple items
    await client.post("/items", json={"name": "Bread", "amount": 1, "store_id": rewe_id, "category_id": bakery_id})
    await client.post("/items", json={"name": "Apples", "amount": 6})
    
    # 1. Test status filter
    response = await client.get("/items?status=new")
    assert len(response.json()) == 2
    
    # 2. Test store ID filter
    response = await client.get(f"/items?store_id={rewe_id}")
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Bread"
    
    # 3. Test category name filter
    response = await client.get("/items?category_name=Bakery")
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Bread"

#
# PET ENDPOINT TESTS
#

async def test_get_pet_fallback(client):
    # Fallback endpoint gets the default pet ('Companion') seeded in test setup
    response = await client.get("/pet")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Companion"
    assert data["id"] == 1
    assert data["is_inside"] is False

async def test_get_all_pets(client):
    response = await client.get("/pets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Companion"

async def test_create_pet_success(client):
    response = await client.post("/pets", json={"name": "Fluffy"})
    assert response.status_code == status.HTTP_201_CREATED
    new_pet = response.json()
    assert new_pet["name"] == "Fluffy"
    assert new_pet["id"] > 1
    
    # Verify in list
    response = await client.get("/pets")
    assert len(response.json()) == 2
    assert any(p["name"] == "Fluffy" for p in response.json())

async def test_create_pet_validation(client):
    response = await client.post("/pets", json={"name": "  "})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_rename_pet(client):
    # Create pet
    res = await client.post("/pets", json={"name": "Rocky"})
    pet_id = res.json()["id"]
    
    # Rename pet
    response = await client.put(f"/pets/{pet_id}", json={"name": "Rocky Balboa"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "Rocky Balboa"
    
    # Verify in DB
    response = await client.get(f"/pets/{pet_id}")
    assert response.json()["name"] == "Rocky Balboa"

async def test_delete_pet(client):
    res = await client.post("/pets", json={"name": "Temporary Pet"})
    pet_id = res.json()["id"]
    
    response = await client.delete(f"/pets/{pet_id}")
    assert response.status_code == status.HTTP_200_OK
    
    # Verify 404
    response = await client.get(f"/pets/{pet_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_toggle_pet_location(client):
    # Toggle 'Companion' (id 1) Location
    response = await client.patch("/pets/1/location")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_inside"] is True
    
    # Check that location change was logged in audit trail
    response = await client.get("/pets/1/logs")
    logs = response.json()
    assert any(log["activity_type"] == "location_change" and "Moved inside" in log["detail"] for log in logs)

async def test_feed_pet(client):
    # Feed 'Companion' (id 1)
    response = await client.post("/pets/1/feed", json={"amount": "double portion"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["amount_fed"] == "double portion"
    
    # Verify persistent state and logging
    response = await client.get("/pets/1")
    assert response.json()["amount_fed"] == "double portion"
    
    response = await client.get("/pets/1/logs")
    logs = response.json()
    assert any(log["activity_type"] == "fed" and "double portion" in log["detail"] for log in logs)


#
# CATEGORY & STORE OPTIMIZATION TESTS
#

async def test_create_category_color_regex_validation(client):
    # Invalid colors should fail with Pydantic 422
    for invalid_color in ["red", "rgb(0,0,0)", "123456", "#12", "#1234", "#1234567"]:
        response = await client.post("/categories", json={"name": "TestColor", "color": invalid_color})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Valid colors should succeed
    for valid_color in ["#fff", "#000", "#123456", "#aBcDeF"]:
        response = await client.post("/categories", json={"name": f"TestColor_{valid_color[1:]}", "color": valid_color})
        assert response.status_code == status.HTTP_201_CREATED

async def test_case_insensitive_name_uniqueness(client):
    # Create store
    response = await client.post("/stores", json={"name": "Aldi"})
    assert response.status_code == status.HTTP_201_CREATED
    
    # Try creating lowercase duplicate - should fail (unique index Lower(name))
    response = await client.post("/stores", json={"name": "aldi"})
    assert response.status_code == status.HTTP_409_CONFLICT

    # Try creating category
    response = await client.post("/categories", json={"name": "Beverages", "color": "#000"})
    assert response.status_code == status.HTTP_201_CREATED

    # Try creating lowercase category duplicate - should fail
    response = await client.post("/categories", json={"name": "beverages", "color": "#fff"})
    assert response.status_code == status.HTTP_409_CONFLICT

async def test_delete_defaults_prevented(client):
    # Attempting to delete category ID 1 ('keine') should return 400
    response = await client.delete("/categories/1")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot delete" in response.json()["detail"]

    # Attempting to delete store ID 1 ('keiner') should return 400
    response = await client.delete("/stores/1")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot delete" in response.json()["detail"]

async def test_delete_store_reassociates_items(client):
    # Create custom store
    await client.post("/stores", json={"name": "Target"})
    response = await client.get("/stores")
    target_store = next(s for s in response.json() if s["name"] == "Target")
    store_id = target_store["id"]

    # Create item associated with the custom store
    await client.post("/items", json={"name": "Product", "amount": 1, "store_id": store_id})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]
    assert response.json()[0]["store_id"] == store_id

    # Delete the custom store
    response = await client.delete(f"/stores/{store_id}")
    assert response.status_code == status.HTTP_200_OK

    # Ensure the item's store reference fallback-reassociated to store 1 ('keiner')
    response = await client.get(f"/items/{item_id}")
    assert response.json()["store_id"] == 1

async def test_delete_category_reassociates_items(client):
    # Create custom category
    await client.post("/categories", json={"name": "Pantry", "color": "#111"})
    response = await client.get("/categories")
    pantry_cat = next(c for c in response.json() if c["name"] == "Pantry")
    cat_id = pantry_cat["id"]

    # Create item associated with the custom category
    await client.post("/items", json={"name": "Product", "amount": 1, "category_id": cat_id})
    response = await client.get("/items")
    item_id = response.json()[0]["id"]
    assert response.json()[0]["category_id"] == cat_id

    # Delete the custom category
    response = await client.delete(f"/categories/{cat_id}")
    assert response.status_code == status.HTTP_200_OK

    # Ensure the item's category reference fallback-reassociated to category 1 ('keine')
    response = await client.get(f"/items/{item_id}")
    assert response.json()["category_id"] == 1

async def test_item_count_aggregation(client):
    # Create custom store & category
    await client.post("/stores", json={"name": "Edeka"})
    response = await client.get("/stores")
    edeka = next(s for s in response.json() if s["name"] == "Edeka")
    store_id = edeka["id"]

    await client.post("/categories", json={"name": "Fruits", "color": "#f00"})
    response = await client.get("/categories")
    fruits = next(c for c in response.json() if c["name"] == "Fruits")
    cat_id = fruits["id"]

    # Assert initial counts are 0
    assert edeka["item_count"] == 0
    assert fruits["item_count"] == 0

    # Add items to the store and category
    await client.post("/items", json={"name": "Banana", "amount": 3, "store_id": store_id, "category_id": cat_id})
    await client.post("/items", json={"name": "Orange", "amount": 2, "store_id": store_id, "category_id": cat_id})

    # Fetch store & category and check aggregated count
    response = await client.get("/stores")
    edeka_updated = next(s for s in response.json() if s["id"] == store_id)
    assert edeka_updated["item_count"] == 2

    response = await client.get("/categories")
    fruits_updated = next(c for c in response.json() if c["id"] == cat_id)
    assert fruits_updated["item_count"] == 2


#
# UX ENHANCEMENT TESTS
#

async def test_item_prediction(client):
    # 1. Setup custom store & category
    await client.post("/stores", json={"name": "Aldi"})
    res = await client.get("/stores")
    aldi_id = next(s["id"] for s in res.json() if s["name"] == "Aldi")

    await client.post("/categories", json={"name": "Produce", "color": "#00ff00"})
    res = await client.get("/categories")
    produce_id = next(c["id"] for c in res.json() if c["name"] == "Produce")

    # 2. Add 'Banana' explicitly associated with Aldi and Produce
    await client.post("/items", json={"name": "Banana", "amount": 1, "store_id": aldi_id, "category_id": produce_id})

    # 3. Add 'Banana' again WITHOUT store/category details
    await client.post("/items", json={"name": "Banana", "amount": 2})

    # 4. Fetch items and verify the second Banana automatically predicted and set Aldi/Produce!
    res = await client.get("/items")
    items = res.json()
    assert len(items) == 2
    banana_auto = next(i for i in items if i["amount"] == 2)
    assert banana_auto["store_id"] == aldi_id
    assert banana_auto["category_id"] == produce_id

async def test_suggest_endpoint(client):
    # 1. Create items with different names and counts to build frequency history
    await client.post("/items", json={"name": "Apfel", "amount": 1})
    await client.post("/items", json={"name": "Apfel", "amount": 2})
    await client.post("/items", json={"name": "Apfelsine", "amount": 1})
    await client.post("/items", json={"name": "Banane", "amount": 1})

    # 2. Call suggest with query 'apf'
    res = await client.get("/items/suggest?q=apf")
    assert res.status_code == status.HTTP_200_OK
    suggestions = res.json()

    # Should match prefix, sort by frequency (Apfel = 2, Apfelsine = 1), and exclude Banane
    assert len(suggestions) == 2
    assert suggestions[0] == "Apfel"
    assert suggestions[1] == "Apfelsine"

async def test_archive_endpoint(client):
    # 1. Create items
    await client.post("/items", json={"name": "Milk", "amount": 1})
    await client.post("/items", json={"name": "Bread", "amount": 1})

    res = await client.get("/items")
    items = res.json()
    milk_id = next(i["id"] for i in items if i["name"] == "Milk")

    # 2. Mark Milk as bought
    await client.patch(f"/items/{milk_id}/status")

    # 3. Archive bought items
    res = await client.post("/items/archive")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["deleted_count"] == 1

    # 4. Verify Bread is still active, Milk is deleted
    res = await client.get("/items")
    remaining = res.json()
    assert len(remaining) == 1
    assert remaining[0]["name"] == "Bread"

async def test_frequent_items_endpoint(client):
    # 1. Create a custom item 'Eggs' and mark it as bought
    await client.post("/items", json={"name": "Eggs", "amount": 12})
    res = await client.get("/items")
    eggs_id = next(i["id"] for i in res.json() if i["name"] == "Eggs")
    await client.patch(f"/items/{eggs_id}/status")  # set status -> bought

    # 2. Call /items/frequent, Eggs should appear since they are not active (status = 'bought')
    res = await client.get("/items/frequent")
    assert res.status_code == status.HTTP_200_OK
    frequent = res.json()
    assert len(frequent) == 1
    assert frequent[0]["name"] == "Eggs"
    assert frequent[0]["purchase_count"] == 1

    # 3. Add Eggs back to the active list
    await client.post("/items", json={"name": "Eggs", "amount": 6})

    # 4. Call /items/frequent, Eggs should now be filtered out because they are active on the list
    res = await client.get("/items/frequent")
    assert len(res.json()) == 0

    # 5. Buy the active Eggs
    res = await client.get("/items")
    active_eggs_id = next(i["id"] for i in res.json() if i["status"] == "new")
    await client.patch(f"/items/{active_eggs_id}/status")

    # 6. Call /items/frequent, Eggs should be back with a purchase count of 2!
    res = await client.get("/items/frequent")
    frequent = res.json()
    assert len(frequent) == 1
    assert frequent[0]["name"] == "Eggs"
    assert frequent[0]["purchase_count"] == 2


#
# RECIPE TESTS
#

async def test_recipe_lifecycle(client):
    # 1. Create Recipe
    recipe_payload = {
        "name": "Spaghetti Bolognese",
        "description": "Tasty italian pasta",
        "ingredients": [
            {"name": "Pasta", "amount": 1, "note": "500g package"},
            {"name": "Ground Beef", "amount": 1, "note": "fresh"}
        ]
    }
    
    response = await client.post("/recipes", json=recipe_payload)
    assert response.status_code == status.HTTP_201_CREATED
    recipe_detail = response.json()
    assert recipe_detail["name"] == "Spaghetti Bolognese"
    assert len(recipe_detail["ingredients"]) == 2
    recipe_id = recipe_detail["id"]

    # 2. Get Recipes List
    response = await client.get("/recipes")
    assert response.status_code == status.HTTP_200_OK
    recipes = response.json()
    assert len(recipes) == 1
    assert recipes[0]["name"] == "Spaghetti Bolognese"

    # 3. Get Recipe Detail
    response = await client.get(f"/recipes/{recipe_id}")
    assert response.status_code == status.HTTP_200_OK
    detail = response.json()
    assert detail["name"] == "Spaghetti Bolognese"
    assert len(detail["ingredients"]) == 2
    assert any(i["name"] == "Pasta" for i in detail["ingredients"])

    # 4. Update Recipe (Rename, edit pasta amount, replaceGround beef with tomato paste)
    update_payload = {
        "name": "Super Spaghetti",
        "description": "Upgraded spaghetti recipe",
        "ingredients": [
            {"name": "Pasta", "amount": 2, "note": "1kg"},
            {"name": "Tomato Paste", "amount": 1}
        ]
    }
    response = await client.put(f"/recipes/{recipe_id}", json=update_payload)
    assert response.status_code == status.HTTP_200_OK
    updated_detail = response.json()
    assert updated_detail["name"] == "Super Spaghetti"
    assert len(updated_detail["ingredients"]) == 2
    assert any(i["name"] == "Tomato Paste" for i in updated_detail["ingredients"])
    assert not any(i["name"] == "Ground Beef" for i in updated_detail["ingredients"])

    # 5. Delete Recipe
    response = await client.delete(f"/recipes/{recipe_id}")
    assert response.status_code == status.HTTP_200_OK

    # 6. Verify Recipe Detail 404s
    response = await client.get(f"/recipes/{recipe_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_add_recipe_to_shopping_list(client):
    # 1. Setup custom store to test prediction integration
    await client.post("/stores", json={"name": "Edeka"})
    res = await client.get("/stores")
    edeka_id = next(s["id"] for s in res.json() if s["name"] == "Edeka")

    # Seed history: add Mozzarella bought at Edeka and mark it as bought
    await client.post("/items", json={"name": "Mozzarella", "amount": 1, "store_id": edeka_id})
    res_items = await client.get("/items")
    mozz_id = next(i["id"] for i in res_items.json() if i["name"] == "Mozzarella" and i["store_id"] == edeka_id)
    await client.patch(f"/items/{mozz_id}/status")

    # 2. Create Recipe with ingredients (not specifying stores)
    recipe_payload = {
        "name": "Pizza Margeritha",
        "description": "Standard pizza",
        "ingredients": [
            {"name": "Pizza Dough", "amount": 1},
            {"name": "Mozzarella", "amount": 2}
        ]
    }
    response = await client.post("/recipes", json=recipe_payload)
    recipe_id = response.json()["id"]

    # 3. Add Recipe ingredients to list
    response = await client.post(f"/recipes/{recipe_id}/add")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["added_count"] == 2

    # 4. Fetch shopping list items and verify prediction
    response = await client.get("/items")
    items = response.json()
    
    # We should have 3 items total (1 from history seeding, 2 from recipe)
    assert len(items) == 3
    
    # Find active items (status = new) added by recipe
    active_items = [i for i in items if i["status"] == "new"]
    assert len(active_items) == 2
    
    pizza_dough = next(i for i in active_items if i["name"] == "Pizza Dough")
    mozzarella = next(i for i in active_items if i["name"] == "Mozzarella")
    
    # Pizza dough should point to default store (1)
    assert pizza_dough["store_id"] == 1
    # Mozzarella should have automatically predicted and pointed to Edeka (edeka_id)!
    assert mozzarella["store_id"] == edeka_id


#
# EXTRA RECIPE COVERAGE TESTS
#

async def test_recipe_validation_errors(client):
    # 1. Empty recipe name should fail (422)
    response = await client.post("/recipes", json={"name": "  ", "description": "some desc", "ingredients": []})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. Empty ingredient name should fail (422)
    response = await client.post("/recipes", json={
        "name": "Validation Recipe",
        "ingredients": [{"name": "  ", "amount": 1}]
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 3. Invalid/negative ingredient amount should fail (422)
    response = await client.post("/recipes", json={
        "name": "Validation Recipe",
        "ingredients": [{"name": "Pasta", "amount": 0}]
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_recipe_name_case_insensitive_uniqueness(client):
    # Create Spaghetti Bolognese
    response = await client.post("/recipes", json={"name": "Spaghetti Bolognese", "ingredients": []})
    assert response.status_code == status.HTTP_201_CREATED

    # Try creating lowercase duplicate - should fail (409)
    response = await client.post("/recipes", json={"name": "spaghetti bolognese", "ingredients": []})
    assert response.status_code == status.HTTP_409_CONFLICT

async def test_recipe_404_scenarios(client):
    # Fetch non-existent recipe ID (9999) -> 404
    response = await client.get("/recipes/9999")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Update non-existent recipe ID (9999) -> 404
    response = await client.put("/recipes/9999", json={"name": "New Name", "ingredients": []})
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Delete non-existent recipe ID (9999) -> 404
    response = await client.delete("/recipes/9999")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Add ingredients of non-existent recipe ID (9999) to shopping list -> 404
    response = await client.post("/recipes/9999/add")
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_recipe_ingredients_category_store_deletion_cascade(client):
    # 1. Setup custom store & category
    await client.post("/stores", json={"name": "Kaufland"})
    res = await client.get("/stores")
    kaufland_id = next(s["id"] for s in res.json() if s["name"] == "Kaufland")

    await client.post("/categories", json={"name": "Canned Goods", "color": "#ff00ff"})
    res = await client.get("/categories")
    canned_id = next(c["id"] for c in res.json() if c["name"] == "Canned Goods")

    # 2. Create recipe using custom store & category for ingredient
    recipe_payload = {
        "name": "Canned Soup",
        "ingredients": [
            {"name": "Tomato Soup", "amount": 2, "store_id": kaufland_id, "category_id": canned_id}
        ]
    }
    response = await client.post("/recipes", json=recipe_payload)
    recipe_id = response.json()["id"]

    # 3. Delete the custom store & category
    await client.delete(f"/stores/{kaufland_id}")
    await client.delete(f"/categories/{canned_id}")

    # 4. Fetch the recipe details, ingredient's store_id/category_id should now be None (NULL)
    response = await client.get(f"/recipes/{recipe_id}")
    assert response.status_code == status.HTTP_200_OK
    ingredients = response.json()["ingredients"]
    assert len(ingredients) == 1
    assert ingredients[0]["store_id"] is None
    assert ingredients[0]["category_id"] is None


#
# IMAGE UPLOAD TESTS
#

async def test_item_image_upload_and_cleanup(client):
    from PIL import Image
    import io
    import os

    # 1. Create item
    await client.post("/items", json={"name": "Milk", "amount": 1})
    res = await client.get("/items")
    item_id = res.json()[0]["id"]

    # 2. Generate dummy image in memory
    img = Image.new("RGB", (10, 10), color="blue")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    # 3. Upload file
    files = {"file": ("test.png", img_bytes, "image/png")}
    response = await client.post(f"/items/{item_id}/image", files=files)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    image_path = data["image_path"]
    assert image_path.startswith("/uploads/")
    assert image_path.endswith(".webp") # verifies conversion to webp

    # 4. Check file exists on disk
    local_path = image_path.lstrip("/")
    assert os.path.exists(local_path)

    # 5. Delete item (should clean up file from disk!)
    response = await client.delete(f"/items/{item_id}")
    assert response.status_code == status.HTTP_200_OK
    assert not os.path.exists(local_path)

async def test_recipe_image_upload_and_delete(client):
    from PIL import Image
    import io
    import os

    # 1. Create recipe
    recipe_payload = {
        "name": "Waffles",
        "description": "Tasty waffles",
        "ingredients": []
    }
    response = await client.post("/recipes", json=recipe_payload)
    recipe_id = response.json()["id"]

    # 2. Generate dummy image
    img = Image.new("RGB", (20, 20), color="yellow")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    # 3. Upload image
    files = {"file": ("waffles.jpg", img_bytes, "image/jpeg")}
    response = await client.post(f"/recipes/{recipe_id}/image", files=files)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    image_path = data["image_path"]
    assert image_path.startswith("/uploads/")
    assert image_path.endswith(".webp")
    
    local_path = image_path.lstrip("/")
    assert os.path.exists(local_path)

    # 4. Delete image only
    response = await client.delete(f"/recipes/{recipe_id}/image")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["image_path"] is None
    assert not os.path.exists(local_path)

async def test_image_upload_validation_failures(client):
    # 1. Create item
    await client.post("/items", json={"name": "Ice Cream", "amount": 1})
    res = await client.get("/items")
    item_id = res.json()[0]["id"]

    # 2. Upload invalid MIME format (e.g. text/plain)
    files = {"file": ("test.txt", b"plain text payload", "text/plain")}
    response = await client.post(f"/items/{item_id}/image", files=files)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unsupported image format" in response.json()["detail"]

    # 3. Upload corrupt image masquerading as PNG
    files = {"file": ("fake.png", b"corrupt-data", "image/png")}
    response = await client.post(f"/items/{item_id}/image", files=files)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid or corrupt image" in response.json()["detail"]


#
# MEAL PLAN TESTS
#

async def test_meal_plan_lifecycle(client):
    # 1. Create a meal plan without a recipe
    response = await client.post("/meal-plans", json={
        "date": "2026-08-01",
        "meal_type": "Frühstück",
        "note": "Simple oatmeal"
    })
    assert response.status_code == status.HTTP_201_CREATED
    plan = response.json()
    assert plan["date"] == "2026-08-01"
    assert plan["meal_type"] == "Frühstück"
    assert plan["recipe_id"] is None
    plan_id = plan["id"]

    # 2. Create a recipe and a meal plan referencing it
    recipe_response = await client.post("/recipes", json={"name": "Pancakes", "ingredients": []})
    recipe_id = recipe_response.json()["id"]

    response = await client.post("/meal-plans", json={
        "date": "2026-08-02",
        "meal_type": "Mittagessen",
        "recipe_id": recipe_id
    })
    assert response.status_code == status.HTTP_201_CREATED
    plan_with_recipe_id = response.json()["id"]

    # 3. List meal plans and verify the embedded recipe detail
    response = await client.get("/meal-plans")
    assert response.status_code == status.HTTP_200_OK
    plans = response.json()
    assert len(plans) == 2

    with_recipe = next(p for p in plans if p["id"] == plan_with_recipe_id)
    assert with_recipe["recipe"] is not None
    assert with_recipe["recipe"]["name"] == "Pancakes"

    without_recipe = next(p for p in plans if p["id"] == plan_id)
    assert without_recipe["recipe"] is None

    # 4. Delete a meal plan and verify it's gone
    response = await client.delete(f"/meal-plans/{plan_id}")
    assert response.status_code == status.HTTP_200_OK

    response = await client.get("/meal-plans")
    assert len(response.json()) == 1

async def test_meal_plan_validation(client):
    # Invalid date format should fail (422)
    response = await client.post("/meal-plans", json={"date": "01-08-2026", "meal_type": "Frühstück"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Invalid meal_type should fail (422)
    response = await client.post("/meal-plans", json={"date": "2026-08-01", "meal_type": "Brunch"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_meal_plan_recipe_not_found(client):
    response = await client.post("/meal-plans", json={
        "date": "2026-08-01",
        "meal_type": "Abendessen",
        "recipe_id": 9999
    })
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_delete_meal_plan_not_found(client):
    response = await client.delete("/meal-plans/9999")
    assert response.status_code == status.HTTP_404_NOT_FOUND




