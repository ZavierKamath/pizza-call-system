"""
Order validation for pizza orders.
Validates pizza configurations, quantities, and pricing.
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP

# Configure logging
logger = logging.getLogger(__name__)


class OrderValidator:
    """
    Validates pizza orders including configurations, pricing, and business rules.
    
    Ensures orders meet menu requirements and business constraints.
    """
    
    def __init__(self):
        """Initialize order validator with menu and business rules."""
        # Menu configuration (would be loaded from database in real system)
        self.menu = {
            "sizes": {
                "small": {"price": 12.99, "name": "Small (10\")", "max_toppings": 5},
                "medium": {"price": 15.99, "name": "Medium (12\")", "max_toppings": 7},
                "large": {"price": 18.99, "name": "Large (14\")", "max_toppings": 10}
            },
            "toppings": {
                "pepperoni": 2.00,
                "mushrooms": 1.50,
                "sausage": 2.00,
                "peppers": 1.50,
                "onions": 1.00,
                "extra_cheese": 2.50,
                "olives": 1.50,
                "ham": 2.00,
                "pineapple": 1.50,
                "anchovies": 2.00
            },
            "crusts": {
                "thin": {"price": 0.00, "name": "Thin Crust"},
                "thick": {"price": 0.00, "name": "Thick Crust"},
                "stuffed": {"price": 2.00, "name": "Stuffed Crust"}
            }
        }
        
        # Business rules
        self.max_pizzas_per_order = 10
        self.max_quantity_per_pizza = 5
        self.minimum_order_total = 15.00
        self.tax_rate = 0.085  # 8.5%
        self.delivery_fee = 2.99
        
        logger.info("OrderValidator initialized")
    
    def validate_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive order validation.
        
        Args:
            order_data (dict): Complete order information
            
        Returns:
            dict: Validation result with details
        """
        try:
            logger.debug(f"Validating order: {order_data}")
            
            pizzas = order_data.get("pizzas", [])
            
            if not pizzas:
                return {
                    "is_valid": False,
                    "errors": ["Order must contain at least one pizza"],
                    "warnings": [],
                    "validated_order": {},
                    "calculated_total": 0.0
                }
            
            # Validate each pizza
            validated_pizzas = []
            all_errors = []
            all_warnings = []
            
            for i, pizza in enumerate(pizzas):
                pizza_validation = self.validate_pizza(pizza, position=i+1)
                
                if pizza_validation["is_valid"]:
                    validated_pizzas.append(pizza_validation["validated_pizza"])
                else:
                    all_errors.extend(pizza_validation["errors"])
                
                all_warnings.extend(pizza_validation.get("warnings", []))
            
            # Validate order-level constraints
            order_validation = self._validate_order_constraints(validated_pizzas)
            all_errors.extend(order_validation.get("errors", []))
            all_warnings.extend(order_validation.get("warnings", []))
            
            # Calculate totals
            calculated_totals = self._calculate_order_totals(validated_pizzas)
            
            # Check minimum order requirement
            if calculated_totals["subtotal"] < self.minimum_order_total:
                all_errors.append(f"Order must be at least ${self.minimum_order_total:.2f} (current: ${calculated_totals['subtotal']:.2f})")
            
            # Compile result
            result = {
                "is_valid": len(all_errors) == 0,
                "errors": all_errors,
                "warnings": all_warnings,
                "validated_order": {
                    "pizzas": validated_pizzas,
                    "totals": calculated_totals
                },
                "calculated_total": calculated_totals["total"]
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
    
    def validate_pizza(self, pizza_data: Dict[str, Any], position: int = 1) -> Dict[str, Any]:
        """
        Validate individual pizza configuration.
        
        Args:
            pizza_data (dict): Pizza configuration
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
            if size not in self.menu["sizes"]:
                errors.append(f"Pizza {position}: Invalid size '{size}'. Available: {', '.join(self.menu['sizes'].keys())}")
            else:
                validated_pizza["size"] = size
                validated_pizza["size_info"] = self.menu["sizes"][size]
            
            # Validate crust
            crust = pizza_data.get("crust", "thin").lower()
            if crust not in self.menu["crusts"]:
                warnings.append(f"Pizza {position}: Invalid crust '{crust}', defaulting to thin crust")
                crust = "thin"
            validated_pizza["crust"] = crust
            validated_pizza["crust_info"] = self.menu["crusts"][crust]
            
            # Validate toppings
            toppings = pizza_data.get("toppings", [])
            validated_toppings = []
            invalid_toppings = []
            
            for topping in toppings:
                topping_clean = topping.lower().replace(" ", "_")
                if topping_clean in self.menu["toppings"]:
                    validated_toppings.append(topping_clean)
                else:
                    invalid_toppings.append(topping)
            
            if invalid_toppings:
                warnings.append(f"Pizza {position}: Unknown toppings ignored: {', '.join(invalid_toppings)}")
            
            # Check topping limits
            if size in self.menu["sizes"]:
                max_toppings = self.menu["sizes"][size]["max_toppings"]
                if len(validated_toppings) > max_toppings:
                    errors.append(f"Pizza {position}: Too many toppings. {size} pizzas can have max {max_toppings} toppings")
            
            validated_pizza["toppings"] = validated_toppings
            
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
                pizza_price = self._calculate_pizza_price(validated_pizza)
                validated_pizza["unit_price"] = pizza_price
                validated_pizza["total_price"] = pizza_price * validated_pizza["quantity"]
            
            # Special instructions
            special_instructions = pizza_data.get("special_instructions", "").strip()
            if special_instructions:
                validated_pizza["special_instructions"] = special_instructions[:200]  # Limit length
                if len(special_instructions) > 200:
                    warnings.append(f"Pizza {position}: Special instructions truncated to 200 characters")
            
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
    
    def _validate_order_constraints(self, pizzas: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    
    def _calculate_pizza_price(self, pizza: Dict[str, Any]) -> float:
        """Calculate price for a single pizza."""
        size = pizza.get("size")
        crust = pizza.get("crust", "thin")
        toppings = pizza.get("toppings", [])
        
        # Base price from size
        base_price = self.menu["sizes"][size]["price"]
        
        # Add crust cost
        crust_price = self.menu["crusts"][crust]["price"]
        
        # Add topping costs
        topping_price = sum(self.menu["toppings"][topping] for topping in toppings)
        
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
            "delivery_fee": delivery_fee,
            "total": float(Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        }
    
    def get_menu_info(self) -> Dict[str, Any]:
        """
        Get current menu information.
        
        Returns:
            dict: Complete menu with prices and options
        """
        return {
            "sizes": self.menu["sizes"],
            "toppings": self.menu["toppings"],
            "crusts": self.menu["crusts"],
            "business_rules": {
                "max_pizzas_per_order": self.max_pizzas_per_order,
                "max_quantity_per_pizza": self.max_quantity_per_pizza,
                "minimum_order_total": self.minimum_order_total,
                "tax_rate": self.tax_rate,
                "delivery_fee": self.delivery_fee
            }
        }
    
    def suggest_popular_combinations(self) -> List[Dict[str, Any]]:
        """
        Get popular pizza combination suggestions.
        
        Returns:
            list: Popular pizza configurations
        """
        return [
            {
                "name": "Pepperoni Classic",
                "size": "large",
                "crust": "thin",
                "toppings": ["pepperoni"],
                "description": "Our most popular pizza"
            },
            {
                "name": "Meat Lovers",
                "size": "large", 
                "crust": "thick",
                "toppings": ["pepperoni", "sausage", "ham"],
                "description": "For serious meat lovers"
            },
            {
                "name": "Veggie Supreme",
                "size": "medium",
                "crust": "thin",
                "toppings": ["mushrooms", "peppers", "onions", "olives"],
                "description": "Fresh vegetables on crispy crust"
            },
            {
                "name": "Hawaiian",
                "size": "medium",
                "crust": "thick",
                "toppings": ["ham", "pineapple"],
                "description": "Sweet and savory combination"
            }
        ]
    
    def validate_modification_request(self, current_order: Dict[str, Any], 
                                    modification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a request to modify an existing order.
        
        Args:
            current_order (dict): Existing order
            modification (dict): Requested changes
            
        Returns:
            dict: Validation result for modification
        """
        try:
            # For demo, support adding pizzas or changing quantities
            if modification.get("action") == "add_pizza":
                new_pizza = modification.get("pizza", {})
                pizza_validation = self.validate_pizza(new_pizza)
                
                if pizza_validation["is_valid"]:
                    # Check if adding this pizza would exceed limits
                    current_pizzas = current_order.get("pizzas", [])
                    current_count = sum(p.get("quantity", 1) for p in current_pizzas)
                    new_count = new_pizza.get("quantity", 1)
                    
                    if current_count + new_count > self.max_pizzas_per_order:
                        return {
                            "is_valid": False,
                            "errors": [f"Adding this pizza would exceed the maximum of {self.max_pizzas_per_order} pizzas per order"]
                        }
                
                return pizza_validation
            
            return {
                "is_valid": False,
                "errors": ["Unsupported modification type"]
            }
            
        except Exception as e:
            logger.error(f"Error validating modification: {e}")
            return {
                "is_valid": False,
                "errors": [f"Modification validation error: {str(e)}"]
            }


# Export main class
__all__ = ["OrderValidator"]