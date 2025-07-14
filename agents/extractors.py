"""
LLM-based extraction services for natural speech processing.
Replaces rigid regex patterns with intelligent language understanding.
"""

import logging
import json
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Standard result format for all extractors."""
    success: bool
    data: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    raw_input: str
    errors: List[str] = None
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.suggestions is None:
            self.suggestions = []


class BaseExtractor:
    """Base class for all LLM-based extractors."""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize base extractor with LLM."""
        import os
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        
        # Use fast, efficient model for extraction tasks
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,  # Low temperature for consistent extraction
            api_key=self.openai_api_key,
            max_tokens=300
        )
        
        logger.debug(f"Initialized {self.__class__.__name__} with LLM")
    
    async def _extract_with_prompt(self, user_input: str, system_prompt: str) -> Dict[str, Any]:
        """Generic extraction method using LLM."""
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Extract from: '{user_input}'")
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # Try to parse JSON response
            try:
                result = json.loads(response.content)
                return result
            except json.JSONDecodeError:
                # If not JSON, return as text
                return {"extracted_text": response.content.strip()}
                
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return {"error": str(e)}


class NameExtractor(BaseExtractor):
    """Extract customer names from natural speech."""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        super().__init__(openai_api_key)
        
        self.system_prompt = """
You are a pizza shop assistant extracting customer names from speech.

TASK: Extract the customer's name from their speech input.

RULES:
- Extract first name and last name if both provided
- Handle common speech patterns like "My name is...", "It's...", "This is..."
- Ignore filler words like "uh", "um", "well"
- If multiple names mentioned, extract the one that seems to be the customer's name
- If unclear or no name found, return null

RESPONSE FORMAT (JSON):
{
    "name": "John Smith" or null,
    "confidence": 0.95,
    "notes": "explanation if needed"
}

EXAMPLES:
Input: "John Smith"
Output: {"name": "John Smith", "confidence": 0.95, "notes": ""}

Input: "My name is Sarah Johnson"  
Output: {"name": "Sarah Johnson", "confidence": 0.98, "notes": ""}

Input: "It's Mike"
Output: {"name": "Mike", "confidence": 0.85, "notes": "First name only"}

Input: "A little 28178 settlers Reserve Way"
Output: {"name": null, "confidence": 0.1, "notes": "No clear name found, seems to be address"}
"""
    
    async def extract_name(self, user_input: str) -> ExtractionResult:
        """Extract customer name from speech input."""
        logger.debug(f"Extracting name from: '{user_input[:50]}...'")
        
        result = await self._extract_with_prompt(user_input, self.system_prompt)
        
        if "error" in result:
            return ExtractionResult(
                success=False,
                data={},
                confidence=0.0,
                raw_input=user_input,
                errors=[result["error"]]
            )
        
        name = result.get("name")
        confidence = result.get("confidence", 0.5)
        
        if name and confidence > 0.5:
            return ExtractionResult(
                success=True,
                data={"name": name},
                confidence=confidence,
                raw_input=user_input
            )
        else:
            return ExtractionResult(
                success=False,
                data={},
                confidence=confidence,
                raw_input=user_input,
                errors=["No clear name found in input"],
                suggestions=["Please provide your name clearly"]
            )


class AddressExtractor(BaseExtractor):
    """Extract street addresses from natural speech."""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        super().__init__(openai_api_key)
        
        self.system_prompt = """
You are a pizza shop assistant extracting delivery addresses from speech.

TASK: Extract street address from customer speech for local pizza delivery.

RULES:
- Extract house number and street name
- Handle spoken numbers: "two eight one" → "281", "one two three" → "123"
- Convert common speech patterns: "settlers Reserve Way" → "Settlers Reserve Way"
- Only need street address - ignore city/state/zip (local delivery)
- Handle variations: "I live at...", "It's...", "My address is..."
- Ignore apartment numbers for now (focus on street)

RESPONSE FORMAT (JSON):
{
    "street": "123 Main Street" or null,
    "confidence": 0.95,
    "notes": "explanation if needed"
}

EXAMPLES:
Input: "28178 settlers Reserve Way"
Output: {"street": "28178 Settlers Reserve Way", "confidence": 0.95, "notes": ""}

Input: "It's two eight one, seven eight settlers Reserve Way"
Output: {"street": "28178 Settlers Reserve Way", "confidence": 0.90, "notes": "Converted spoken numbers"}

Input: "I live at 456 Oak Avenue"
Output: {"street": "456 Oak Avenue", "confidence": 0.95, "notes": ""}

Input: "Xavier Camas"
Output: {"street": null, "confidence": 0.1, "notes": "Appears to be a name, not address"}

Input: "Can I have one medium pepperoni pizza"
Output: {"street": null, "confidence": 0.05, "notes": "This is a pizza order, not address"}
"""
    
    async def extract_address(self, user_input: str) -> ExtractionResult:
        """Extract street address from speech input."""
        logger.debug(f"Extracting address from: '{user_input[:50]}...'")
        
        result = await self._extract_with_prompt(user_input, self.system_prompt)
        
        if "error" in result:
            return ExtractionResult(
                success=False,
                data={},
                confidence=0.0,
                raw_input=user_input,
                errors=[result["error"]]
            )
        
        street = result.get("street")
        confidence = result.get("confidence", 0.5)
        
        if street and confidence > 0.6:  # Slightly higher threshold for addresses
            return ExtractionResult(
                success=True,
                data={"street": street},
                confidence=confidence,
                raw_input=user_input
            )
        else:
            return ExtractionResult(
                success=False,
                data={},
                confidence=confidence,
                raw_input=user_input,
                errors=["No clear street address found in input"],
                suggestions=["Please provide your street address with house number and street name"]
            )


class PizzaOrderExtractor(BaseExtractor):
    """Extract pizza order details from natural speech."""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        super().__init__(openai_api_key)
        
        self.system_prompt = """
You are a pizza shop assistant extracting pizza orders from speech.

TASK: Extract pizza order details from customer speech.

MENU REFERENCE:
Sizes: small, medium, large
Toppings: pepperoni, sausage, ham, mushrooms, peppers, onions, olives, extra cheese, pineapple, anchovies
Crusts: thin, thick, stuffed

RULES:
- Extract size, toppings, crust, quantity from speech
- Handle variations: "pep" → "pepperoni", "veggies" → "peppers, mushrooms, onions"
- Default quantity to 1 if not specified
- Default crust to "thin" if not specified
- If no size specified, ask for clarification
- Ignore non-pizza items for now

RESPONSE FORMAT (JSON):
{
    "size": "medium" or null,
    "toppings": ["pepperoni"] or [],
    "crust": "thin",
    "quantity": 1,
    "confidence": 0.95,
    "notes": "explanation if needed"
}

EXAMPLES:
Input: "Can I have one medium pepperoni pizza?"
Output: {"size": "medium", "toppings": ["pepperoni"], "crust": "thin", "quantity": 1, "confidence": 0.95, "notes": ""}

Input: "Let me get a large with mushrooms and olives"
Output: {"size": "large", "toppings": ["mushrooms", "olives"], "crust": "thin", "quantity": 1, "confidence": 0.90, "notes": ""}

Input: "Two small cheese pizzas"
Output: {"size": "small", "toppings": ["cheese"], "crust": "thin", "quantity": 2, "confidence": 0.92, "notes": ""}

Input: "Medium"
Output: {"size": "medium", "toppings": [], "crust": "thin", "quantity": 1, "confidence": 0.80, "notes": "Size only, need toppings"}

Input: "What's your address?"
Output: {"size": null, "toppings": [], "crust": "thin", "quantity": 0, "confidence": 0.05, "notes": "Not a pizza order"}
"""
    
    async def extract_pizza_order(self, user_input: str) -> ExtractionResult:
        """Extract pizza order from speech input."""
        logger.debug(f"Extracting pizza order from: '{user_input[:50]}...'")
        
        result = await self._extract_with_prompt(user_input, self.system_prompt)
        
        if "error" in result:
            return ExtractionResult(
                success=False,
                data={},
                confidence=0.0,
                raw_input=user_input,
                errors=[result["error"]]
            )
        
        confidence = result.get("confidence", 0.5)
        
        # Consider it a pizza order if we found a size or toppings and confidence > 0.6
        has_size = result.get("size") is not None
        has_toppings = len(result.get("toppings", [])) > 0
        is_pizza_order = (has_size or has_toppings) and confidence > 0.6
        
        if is_pizza_order:
            return ExtractionResult(
                success=True,
                data={
                    "size": result.get("size"),
                    "toppings": result.get("toppings", []),
                    "crust": result.get("crust", "thin"),
                    "quantity": result.get("quantity", 1)
                },
                confidence=confidence,
                raw_input=user_input
            )
        else:
            return ExtractionResult(
                success=False,
                data={},
                confidence=confidence,
                raw_input=user_input,
                errors=["No clear pizza order found in input"],
                suggestions=["Please specify pizza size and toppings"]
            )


class PaymentExtractor(BaseExtractor):
    """Extract payment preferences from natural speech."""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        super().__init__(openai_api_key)
        
        self.system_prompt = """
You are a pizza shop assistant extracting payment preferences from speech.

TASK: Extract payment method from customer speech.

ACCEPTED METHODS: cash, credit card, debit card

RULES:
- Look for payment method indicators
- Handle variations: "cash on delivery" → "cash", "card" → "credit card"
- Default to null if unclear
- Ignore unrelated speech

RESPONSE FORMAT (JSON):
{
    "payment_method": "cash" or "credit card" or "debit card" or null,
    "confidence": 0.95,
    "notes": "explanation if needed"
}

EXAMPLES:
Input: "I'll pay by cash"
Output: {"payment_method": "cash", "confidence": 0.95, "notes": ""}

Input: "Credit card"
Output: {"payment_method": "credit card", "confidence": 0.95, "notes": ""}

Input: "Can I use my card?"
Output: {"payment_method": "credit card", "confidence": 0.85, "notes": "Assuming credit card"}

Input: "Thin crust please"
Output: {"payment_method": null, "confidence": 0.05, "notes": "Not payment related"}
"""
    
    async def extract_payment(self, user_input: str) -> ExtractionResult:
        """Extract payment method from speech input."""
        logger.debug(f"Extracting payment from: '{user_input[:50]}...'")
        
        result = await self._extract_with_prompt(user_input, self.system_prompt)
        
        if "error" in result:
            return ExtractionResult(
                success=False,
                data={},
                confidence=0.0,
                raw_input=user_input,
                errors=[result["error"]]
            )
        
        payment_method = result.get("payment_method")
        confidence = result.get("confidence", 0.5)
        
        if payment_method and confidence > 0.7:
            return ExtractionResult(
                success=True,
                data={"payment_method": payment_method},
                confidence=confidence,
                raw_input=user_input
            )
        else:
            return ExtractionResult(
                success=False,
                data={},
                confidence=confidence,
                raw_input=user_input,
                errors=["No clear payment method found in input"],
                suggestions=["Please specify cash, credit card, or debit card"]
            )


# Utility functions that create extractors with proper API key
async def extract_name(user_input: str, openai_api_key: Optional[str] = None) -> ExtractionResult:
    """Utility function to extract names."""
    extractor = NameExtractor(openai_api_key)
    return await extractor.extract_name(user_input)


async def extract_address(user_input: str, openai_api_key: Optional[str] = None) -> ExtractionResult:
    """Utility function to extract addresses."""
    extractor = AddressExtractor(openai_api_key)
    return await extractor.extract_address(user_input)


async def extract_pizza_order(user_input: str, openai_api_key: Optional[str] = None) -> ExtractionResult:
    """Utility function to extract pizza orders."""
    extractor = PizzaOrderExtractor(openai_api_key)
    return await extractor.extract_pizza_order(user_input)


async def extract_payment(user_input: str, openai_api_key: Optional[str] = None) -> ExtractionResult:
    """Utility function to extract payment preferences."""
    extractor = PaymentExtractor(openai_api_key)
    return await extractor.extract_payment(user_input)


# Export main components
__all__ = [
    "ExtractionResult", "BaseExtractor", 
    "NameExtractor", "AddressExtractor", "PizzaOrderExtractor", "PaymentExtractor",
    "extract_name", "extract_address", "extract_pizza_order", "extract_payment"
]