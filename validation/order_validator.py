"""
Order validation for pizza orders with dynamic menu management.
Validates pizza configurations, quantities, pricing, and menu availability.
"""

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Set
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta

from ..config.settings import settings
from ..database.redis_client import get_redis_async
from ..agents.states import StateManager

# Configure logging
logger = logging.getLogger(__name__)


class OrderValidator:
    """
    Validates pizza orders including configurations, pricing, and business rules.
    
    Features dynamic menu loading, availability checking, and real-time price calculation.
    Integrates with business constraints and promotional pricing.
    """
    
    def __init__(self):
        """Initialize order validator with menu and business rules."""
        # Business rules from settings
        self.max_pizzas_per_order = settings.max_pizzas_per_order  # 10 from settings
        self.max_quantity_per_pizza = 5
        self.minimum_order_total = 15.00
        self.tax_rate = 0.085  # 8.5%
        self.delivery_fee = 2.99
        
        # Menu cache configuration
        self.menu_cache_ttl_minutes = 30
        self._cached_menu = None
        self._menu_cache_time = None
        
        # Default menu structure (fallback when dynamic loading fails)
        self.default_menu = {
            "sizes": {
                "small": {
                    "price": 12.99, 
                    "name": "Small (10\")", 
                    "max_toppings": 5,
                    "available": True,
                    "description": "Perfect for 1-2 people"
                },
                "medium": {
                    "price": 15.99, 
                    "name": "Medium (12\")", 
                    "max_toppings": 7,
                    "available": True,
                    "description": "Great for 2-3 people"
                },
                "large": {
                    "price": 18.99, 
                    "name": "Large (14\")", 
                    "max_toppings": 10,
                    "available": True,
                    "description": "Feeds 3-4 people"
                }
            },
            "toppings": {
                "pepperoni": {"price": 2.00, "available": True, "vegetarian": False, "category": "meat"},
                "mushrooms": {"price": 1.50, "available": True, "vegetarian": True, "category": "vegetable"},
                "sausage": {"price": 2.00, "available": True, "vegetarian": False, "category": "meat"},
                "peppers": {"price": 1.50, "available": True, "vegetarian": True, "category": "vegetable"},
                "onions": {"price": 1.00, "available": True, "vegetarian": True, "category": "vegetable"},
                "extra_cheese": {"price": 2.50, "available": True, "vegetarian": True, "category": "cheese"},
                "olives": {"price": 1.50, "available": True, "vegetarian": True, "category": "vegetable"},
                "ham": {"price": 2.00, "available": True, "vegetarian": False, "category": "meat"},
                "pineapple": {"price": 1.50, "available": True, "vegetarian": True, "category": "fruit"},
                "anchovies": {"price": 2.00, "available": True, "vegetarian": False, "category": "seafood"},
                "bacon": {"price": 2.50, "available": True, "vegetarian": False, "category": "meat"},
                "chicken": {"price": 2.25, "available": True, "vegetarian": False, "category": "meat"},
                "spinach": {"price": 1.25, "available": True, "vegetarian": True, "category": "vegetable"},
                "tomatoes": {"price": 1.00, "available": True, "vegetarian": True, "category": "vegetable"},
                "jalapeños": {"price": 1.25, "available": True, "vegetarian": True, "category": "vegetable"}
            },
            "crusts": {
                "thin": {"price": 0.00, "name": "Thin Crust", "available": True, "description": "Light and crispy"},
                "thick": {"price": 0.00, "name": "Thick Crust", "available": True, "description": "Traditional thick crust"},
                "stuffed": {"price": 2.00, "name": "Stuffed Crust", "available": True, "description": "Cheese-stuffed crust"},
                "gluten_free": {"price": 3.00, "name": "Gluten Free", "available": True, "description": "Gluten-free alternative"}
            },
            "specials": [
                {
                    "id": "pepperoni_special",
                    "name": "Pepperoni Special",
                    "description": "Large pepperoni pizza with extra cheese",
                    "price": 19.99,
                    "original_price": 22.49,
                    "available": True,
                    "valid_until": "2024-12-31",
                    "pizza": {
                        "size": "large",
                        "crust": "thin",
                        "toppings": ["pepperoni", "extra_cheese"]
                    }
                }
            ]
        }
        
        # Unavailable items (simulating temporary outages)
        self.temporarily_unavailable = set()
        
        logger.info(f"OrderValidator initialized with max {self.max_pizzas_per_order} pizzas per order")
    
    async def validate_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive order validation with menu availability checking.
        
        Args:
            order_data (dict): Complete order information
            
        Returns:
            dict: Validation result with details and calculated pricing
        """
        try:
            logger.debug(f"Validating order: {order_data}")
            
            # Load current menu
            menu = await self.get_current_menu()
            
            pizzas = order_data.get("pizzas", [])
            
            if not pizzas:
                return {
                    "is_valid": False,
                    "errors": ["Order must contain at least one pizza"],
                    "warnings": [],
                    "validated_order": {},
                    "calculated_total": 0.0,
                    "menu_suggestions": await self._get_popular_suggestions()
                }
            
            # Validate each pizza
            validated_pizzas = []
            all_errors = []
            all_warnings = []
            
            for i, pizza in enumerate(pizzas):
                pizza_validation = await self.validate_pizza(pizza, menu, position=i+1)
                
                if pizza_validation["is_valid"]:
                    validated_pizzas.append(pizza_validation["validated_pizza"])
                else:
                    all_errors.extend(pizza_validation["errors"])
                
                all_warnings.extend(pizza_validation.get("warnings", []))
            
            # Validate order-level constraints
            order_validation = await self._validate_order_constraints(validated_pizzas)
            all_errors.extend(order_validation.get("errors", []))
            all_warnings.extend(order_validation.get("warnings", []))
            
            # Calculate totals
            calculated_totals = self._calculate_order_totals(validated_pizzas)
            
            # Check minimum order requirement
            if calculated_totals["subtotal"] < self.minimum_order_total:
                all_errors.append(
                    f"Order must be at least ${self.minimum_order_total:.2f} "
                    f"(current: ${calculated_totals['subtotal']:.2f})"
                )
            
            # Check for available promotions
            promotion_info = await self._check_applicable_promotions(validated_pizzas, calculated_totals)
            if promotion_info["applicable_promotions"]:
                all_warnings.extend(promotion_info["suggestions"])
            
            # Compile result
            result = {
                "is_valid": len(all_errors) == 0,
                "errors": all_errors,
                "warnings": all_warnings,
                "validated_order": {
                    "pizzas": validated_pizzas,
                    "totals": calculated_totals,
                    "promotions": promotion_info["applicable_promotions"]
                },
                "calculated_total": calculated_totals["total"],
                "menu_info": {
                    "unavailable_items": list(self.temporarily_unavailable),
                    "special_offers": menu.get("specials", [])
                }
            }
            
            if result["is_valid"]:
                logger.info(f"Order validation successful: {len(validated_pizzas)} pizzas, total ${calculated_totals['total']:.2f}")
            else:
                logger.warning(f"Order validation failed: {all_errors}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating order: {e}")
            return {
                "is_valid": False,
                "errors": [f"Order validation error: {str(e)}"],
                "warnings": [],
                "validated_order": {},
                "calculated_total": 0.0
            }
    
    async def validate_pizza(self, pizza_data: Dict[str, Any], menu: Dict[str, Any], position: int = 1) -> Dict[str, Any]:
        """
        Validate individual pizza configuration against current menu.
        
        Args:
            pizza_data (dict): Pizza configuration
            menu (dict): Current menu data
            position (int): Pizza position in order (for error messages)
            
        Returns:
            dict: Pizza validation result
        """
        try:
            errors = []
            warnings = []
            validated_pizza = {}
            
            # Validate size
            size = pizza_data.get("size", "").lower()
            if size not in menu["sizes"]:
                available_sizes = [s for s, info in menu["sizes"].items() if info.get("available", True)]
                errors.append(f"Pizza {position}: Invalid size '{size}'. Available: {', '.join(available_sizes)}")
            elif not menu["sizes"][size].get("available", True):
                errors.append(f"Pizza {position}: Size '{size}' is currently unavailable")
            else:
                validated_pizza["size"] = size
                validated_pizza["size_info"] = menu["sizes"][size]
            
            # Validate crust
            crust = pizza_data.get("crust", "thin").lower()
            if crust not in menu["crusts"]:
                available_crusts = [c for c, info in menu["crusts"].items() if info.get("available", True)]
                warnings.append(f"Pizza {position}: Invalid crust '{crust}', defaulting to thin crust")
                crust = "thin"
            elif not menu["crusts"][crust].get("available", True):
                warnings.append(f"Pizza {position}: Crust '{crust}' unavailable, using thin crust")
                crust = "thin"
            
            validated_pizza["crust"] = crust
            validated_pizza["crust_info"] = menu["crusts"][crust]
            
            # Validate toppings with availability checking
            toppings = pizza_data.get("toppings", [])
            validated_toppings = []
            invalid_toppings = []
            unavailable_toppings = []
            
            for topping in toppings:
                topping_clean = topping.lower().replace(" ", "_")
                
                if topping_clean not in menu["toppings"]:
                    invalid_toppings.append(topping)
                elif not menu["toppings"][topping_clean].get("available", True):
                    unavailable_toppings.append(topping)
                elif topping_clean in self.temporarily_unavailable:
                    unavailable_toppings.append(topping)
                else:
                    validated_toppings.append(topping_clean)
            
            if invalid_toppings:
                warnings.append(f"Pizza {position}: Unknown toppings ignored: {', '.join(invalid_toppings)}")
            
            if unavailable_toppings:
                warnings.append(f"Pizza {position}: Unavailable toppings removed: {', '.join(unavailable_toppings)}")
            
            # Check topping limits
            if size in menu["sizes"]:
                max_toppings = menu["sizes"][size].get("max_toppings", 10)
                if len(validated_toppings) > max_toppings:
                    errors.append(f"Pizza {position}: Too many toppings. {size} pizzas can have max {max_toppings} toppings (you have {len(validated_toppings)})")
            
            validated_pizza["toppings"] = validated_toppings
            validated_pizza["topping_info"] = {
                topping: menu["toppings"][topping] for topping in validated_toppings
            }
            
            # Validate quantity
            quantity = pizza_data.get("quantity", 1)
            try:
                quantity = int(quantity)
                if quantity < 1:
                    errors.append(f"Pizza {position}: Quantity must be at least 1")
                elif quantity > self.max_quantity_per_pizza:
                    errors.append(f"Pizza {position}: Maximum quantity per pizza is {self.max_quantity_per_pizza}")
                else:
                    validated_pizza["quantity"] = quantity
            except (ValueError, TypeError):
                errors.append(f"Pizza {position}: Invalid quantity '{quantity}'")
            
            # Calculate pizza price
            if "size" in validated_pizza and "quantity" in validated_pizza:
                pizza_price = self._calculate_pizza_price(validated_pizza, menu)
                validated_pizza["unit_price"] = pizza_price
                validated_pizza["total_price"] = pizza_price * validated_pizza["quantity"]
            
            # Special instructions
            special_instructions = pizza_data.get("special_instructions", "").strip()
            if special_instructions:
                validated_pizza["special_instructions"] = special_instructions[:200]  # Limit length
                if len(special_instructions) > 200:
                    warnings.append(f"Pizza {position}: Special instructions truncated to 200 characters")
            
            # Add dietary information
            validated_pizza["dietary_info"] = self._calculate_dietary_info(validated_toppings, menu)
            
            return {
                "is_valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "validated_pizza": validated_pizza if len(errors) == 0 else {}
            }
            
        except Exception as e:
            logger.error(f"Error validating pizza {position}: {e}")
            return {
                "is_valid": False,
                "errors": [f"Pizza {position}: Validation error - {str(e)}"],
                "warnings": [],
                "validated_pizza": {}
            }
    
    async def check_menu_availability(self) -> Dict[str, Any]:
        """
        Check current menu availability and return status.
        
        Returns:
            dict: Menu availability status
        """
        try:
            menu = await self.get_current_menu()
            
            unavailable_items = {
                "sizes": [size for size, info in menu["sizes"].items() if not info.get("available", True)],
                "crusts": [crust for crust, info in menu["crusts"].items() if not info.get("available", True)],
                "toppings": [topping for topping, info in menu["toppings"].items() if not info.get("available", True)]
            }
            
            return {
                "menu_available": True,
                "unavailable_items": unavailable_items,
                "temporarily_unavailable": list(self.temporarily_unavailable),
                "last_updated": datetime.utcnow().isoformat(),
                "special_offers": len(menu.get("specials", []))
            }
            
        except Exception as e:
            logger.error(f"Error checking menu availability: {e}")
            return {
                "menu_available": False,
                "error": str(e),
                "unavailable_items": {},
                "temporarily_unavailable": []
            }
    
    async def get_current_menu(self) -> Dict[str, Any]:
        """
        Get current menu with caching and real-time availability.
        
        Returns:
            dict: Current menu data
        """
        try:
            # Check cache first
            if self._cached_menu and self._menu_cache_time:
                cache_age = datetime.utcnow() - self._menu_cache_time
                if cache_age < timedelta(minutes=self.menu_cache_ttl_minutes):
                    return self._cached_menu
            
            # Try to load from Redis (dynamic menu updates)
            menu = await self._load_menu_from_redis()
            if menu:
                self._cached_menu = menu
                self._menu_cache_time = datetime.utcnow()
                return menu
            
            # Fallback to default menu
            logger.info("Using default menu (dynamic menu not available)")
            self._cached_menu = self.default_menu.copy()
            self._menu_cache_time = datetime.utcnow()
            
            return self._cached_menu
            
        except Exception as e:
            logger.error(f"Error loading menu: {e}")
            return self.default_menu.copy()
    
    async def update_item_availability(self, item_type: str, item_name: str, available: bool) -> bool:
        """
        Update availability of a menu item.
        
        Args:
            item_type (str): Type of item (size, crust, topping)
            item_name (str): Name of the item
            available (bool): Availability status
            
        Returns:
            bool: True if updated successfully
        """
        try:
            if available:
                self.temporarily_unavailable.discard(item_name)
            else:
                self.temporarily_unavailable.add(item_name)
            
            # Update Redis cache
            await self._update_menu_in_redis(item_type, item_name, available)
            
            # Clear local cache to force reload
            self._cached_menu = None
            self._menu_cache_time = None
            
            logger.info(f"Updated {item_type} '{item_name}' availability: {available}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating item availability: {e}")
            return False
    
    def calculate_order_total(self, pizzas: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate order totals for validated pizzas.
        
        Args:
            pizzas (list): List of validated pizzas
            
        Returns:
            dict: Order total breakdown
        """
        return self._calculate_order_totals(pizzas)
    
    async def get_menu_suggestions(self, dietary_preferences: List[str] = None) -> List[Dict[str, Any]]:
        """
        Get menu suggestions based on dietary preferences.
        
        Args:
            dietary_preferences (list): List of dietary preferences (vegetarian, etc.)
            
        Returns:
            list: List of suggested pizza combinations
        """
        try:
            menu = await self.get_current_menu()
            suggestions = []
            
            # Popular combinations
            popular_combos = [
                {
                    "name": "Pepperoni Classic",
                    "size": "large",
                    "crust": "thin",
                    "toppings": ["pepperoni"],
                    "description": "Our most popular pizza",
                    "estimated_price": None
                },
                {
                    "name": "Meat Lovers",
                    "size": "large", 
                    "crust": "thick",
                    "toppings": ["pepperoni", "sausage", "ham"],
                    "description": "For serious meat lovers",
                    "estimated_price": None
                },
                {
                    "name": "Veggie Supreme",
                    "size": "medium",
                    "crust": "thin",
                    "toppings": ["mushrooms", "peppers", "onions", "olives"],
                    "description": "Fresh vegetables on crispy crust",
                    "estimated_price": None
                },
                {
                    "name": "Hawaiian",
                    "size": "medium",
                    "crust": "thick",
                    "toppings": ["ham", "pineapple"],
                    "description": "Sweet and savory combination",
                    "estimated_price": None
                }
            ]
            
            for combo in popular_combos:
                # Check availability
                if self._check_combo_availability(combo, menu):
                    # Calculate price
                    combo["estimated_price"] = self._calculate_pizza_price({
                        "size": combo["size"],
                        "crust": combo["crust"],
                        "toppings": combo["toppings"],
                        "quantity": 1
                    }, menu)
                    
                    # Filter by dietary preferences
                    if dietary_preferences:
                        if "vegetarian" in dietary_preferences:
                            is_vegetarian = all(
                                menu["toppings"].get(topping, {}).get("vegetarian", False)
                                for topping in combo["toppings"]
                            )
                            if is_vegetarian:
                                suggestions.append(combo)
                        else:
                            suggestions.append(combo)
                    else:
                        suggestions.append(combo)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting menu suggestions: {e}")
            return []
    
    async def _validate_order_constraints(self, pizzas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate order-level business constraints."""
        errors = []
        warnings = []
        
        # Check maximum pizzas per order
        total_pizza_count = sum(pizza.get("quantity", 1) for pizza in pizzas)
        if total_pizza_count > self.max_pizzas_per_order:
            errors.append(f"Order exceeds maximum of {self.max_pizzas_per_order} pizzas (current: {total_pizza_count})")
        
        # Check for duplicate pizzas (could suggest combining)
        pizza_configs = []
        for pizza in pizzas:
            config_key = f"{pizza.get('size')}-{pizza.get('crust')}-{sorted(pizza.get('toppings', []))}"
            if config_key in pizza_configs:
                warnings.append("Order contains duplicate pizza configurations - consider combining quantities")
            pizza_configs.append(config_key)
        
        return {"errors": errors, "warnings": warnings}
    
    def _calculate_pizza_price(self, pizza: Dict[str, Any], menu: Optional[Dict[str, Any]] = None) -> float:
        """Calculate price for a single pizza using current menu."""
        if menu is None:
            menu = self.default_menu
        
        size = pizza.get("size")
        crust = pizza.get("crust", "thin")
        toppings = pizza.get("toppings", [])
        
        # Base price from size
        base_price = menu["sizes"][size]["price"]
        
        # Add crust cost
        crust_price = menu["crusts"][crust]["price"]
        
        # Add topping costs
        topping_price = sum(
            menu["toppings"].get(topping, {}).get("price", 0.0) 
            for topping in toppings
        )
        
        total_price = base_price + crust_price + topping_price
        
        # Round to 2 decimal places
        return float(Decimal(str(total_price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    
    def _calculate_order_totals(self, pizzas: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate complete order totals including tax and fees."""
        subtotal = sum(pizza.get("total_price", 0.0) for pizza in pizzas)
        
        # Calculate tax
        tax = subtotal * self.tax_rate
        
        # Add delivery fee
        delivery_fee = self.delivery_fee
        
        # Calculate total
        total = subtotal + tax + delivery_fee
        
        # Round all values
        return {
            "subtotal": float(Decimal(str(subtotal)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "tax": float(Decimal(str(tax)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "tax_rate": self.tax_rate,
            "delivery_fee": delivery_fee,
            "total": float(Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        }
    
    def _calculate_dietary_info(self, toppings: List[str], menu: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate dietary information for a pizza."""
        is_vegetarian = all(
            menu["toppings"].get(topping, {}).get("vegetarian", False)
            for topping in toppings
        )
        
        categories = set()
        for topping in toppings:
            category = menu["toppings"].get(topping, {}).get("category", "unknown")
            categories.add(category)
        
        return {
            "vegetarian": is_vegetarian,
            "has_meat": "meat" in categories or "seafood" in categories,
            "has_dairy": "cheese" in categories,
            "categories": list(categories)
        }
    
    def _check_combo_availability(self, combo: Dict[str, Any], menu: Dict[str, Any]) -> bool:
        """Check if a pizza combination is available."""
        # Check size availability
        if not menu["sizes"].get(combo["size"], {}).get("available", False):
            return False
        
        # Check crust availability
        if not menu["crusts"].get(combo["crust"], {}).get("available", False):
            return False
        
        # Check topping availability
        for topping in combo.get("toppings", []):
            if not menu["toppings"].get(topping, {}).get("available", False):
                return False
            if topping in self.temporarily_unavailable:
                return False
        
        return True
    
    async def _check_applicable_promotions(self, pizzas: List[Dict[str, Any]], totals: Dict[str, float]) -> Dict[str, Any]:
        """Check for applicable promotions and discounts."""
        try:
            menu = await self.get_current_menu()
            applicable_promotions = []
            suggestions = []
            
            # Check special offers
            for special in menu.get("specials", []):
                if special.get("available", False):
                    # Simple promotion logic - can be expanded
                    if totals["subtotal"] >= 25.00:  # Minimum for promotions
                        suggestions.append(f"Add {special['name']} for just ${special['price']:.2f} (save ${special.get('original_price', special['price']) - special['price']:.2f})")
            
            return {
                "applicable_promotions": applicable_promotions,
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error checking promotions: {e}")
            return {"applicable_promotions": [], "suggestions": []}
    
    async def _get_popular_suggestions(self) -> List[Dict[str, Any]]:
        """Get popular pizza suggestions for empty orders."""
        return await self.get_menu_suggestions()
    
    async def _load_menu_from_redis(self) -> Optional[Dict[str, Any]]:
        """Load dynamic menu from Redis cache."""
        try:
            redis_client = await get_redis_async()
            with redis_client.get_connection() as conn:
                menu_data = conn.get("pizza_menu:current")
                if menu_data:
                    return json.loads(menu_data)
            return None
            
        except Exception as e:
            logger.warning(f"Could not load menu from Redis: {e}")
            return None
    
    async def _update_menu_in_redis(self, item_type: str, item_name: str, available: bool) -> None:
        """Update menu item availability in Redis."""
        try:
            redis_client = await get_redis_async()
            availability_key = f"pizza_menu:availability:{item_type}:{item_name}"
            
            with redis_client.get_connection() as conn:
                conn.setex(availability_key, 3600, "available" if available else "unavailable")  # 1 hour TTL
                
        except Exception as e:
            logger.warning(f"Could not update menu in Redis: {e}")


# Create global validator instance
order_validator = OrderValidator()


# Utility functions for integration
async def validate_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Utility function for order validation."""
    return await order_validator.validate_order(order_data)


async def validate_pizza(pizza_data: Dict[str, Any], position: int = 1) -> Dict[str, Any]:
    """Utility function for pizza validation."""
    menu = await order_validator.get_current_menu()
    return await order_validator.validate_pizza(pizza_data, menu, position)


async def get_menu_info() -> Dict[str, Any]:
    """Utility function to get current menu information."""
    return await order_validator.get_current_menu()


async def check_menu_availability() -> Dict[str, Any]:
    """Utility function to check menu availability."""
    return await order_validator.check_menu_availability()


async def get_menu_suggestions(dietary_preferences: List[str] = None) -> List[Dict[str, Any]]:
    """Utility function to get menu suggestions."""
    return await order_validator.get_menu_suggestions(dietary_preferences)


def calculate_order_total(pizzas: List[Dict[str, Any]]) -> Dict[str, float]:
    """Utility function to calculate order totals."""
    return order_validator.calculate_order_total(pizzas)


# Export main components
__all__ = [
    "OrderValidator", "order_validator", "validate_order", "validate_pizza", 
    "get_menu_info", "check_menu_availability", "get_menu_suggestions", "calculate_order_total"
]