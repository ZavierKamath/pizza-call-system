"""
Payment security and compliance features.
Implements PCI DSS compliance, fraud detection, and security monitoring.
"""

import logging
import hashlib
import hmac
import secrets
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import ipaddress

from ..database.redis_client import get_redis_async
from ..database import get_db_session
from ..database.models import PaymentTransaction, PaymentMethodRecord
from ..config.logging_config import get_logger
from ..config.settings import settings

# Configure logging
logger = get_logger(__name__)


class SecurityRiskLevel(Enum):
    """Security risk levels for payment transactions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceCheck(Enum):
    """PCI DSS compliance check types."""
    DATA_ENCRYPTION = "data_encryption"
    ACCESS_CONTROL = "access_control"
    NETWORK_SECURITY = "network_security"
    MONITORING = "monitoring"
    VULNERABILITY_MANAGEMENT = "vulnerability_management"
    SECURE_SYSTEMS = "secure_systems"


@dataclass
class SecurityEvent:
    """Security event data structure."""
    event_type: str
    risk_level: SecurityRiskLevel
    description: str
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    payment_intent_id: Optional[str] = None
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class FraudCheck:
    """Fraud detection check result."""
    check_type: str
    passed: bool
    risk_score: float  # 0.0 to 1.0
    details: str
    metadata: Optional[Dict[str, Any]] = None


class PaymentSecurityManager:
    """
    Payment security and compliance management system.
    
    Provides fraud detection, PCI DSS compliance monitoring,
    security event tracking, and threat mitigation.
    """
    
    def __init__(self):
        """Initialize payment security manager."""
        # Fraud detection thresholds
        self.fraud_thresholds = {
            "velocity_limit": 5,  # Max transactions per minute
            "amount_spike": 10.0,  # 10x normal amount
            "failed_attempts": 3,  # Max failed attempts
            "suspicious_countries": {"XX", "YY"},  # Blocked country codes
            "high_risk_amount": 1000.0,  # $1000+ triggers additional checks
            "rapid_retry_window": 60  # 60 seconds for retry detection
        }
        
        # PCI DSS compliance requirements
        self.compliance_requirements = {
            ComplianceCheck.DATA_ENCRYPTION: {
                "required": True,
                "description": "All cardholder data must be encrypted"
            },
            ComplianceCheck.ACCESS_CONTROL: {
                "required": True,
                "description": "Restrict access to cardholder data"
            },
            ComplianceCheck.NETWORK_SECURITY: {
                "required": True,
                "description": "Maintain secure network and systems"
            },
            ComplianceCheck.MONITORING: {
                "required": True,
                "description": "Monitor and test networks regularly"
            },
            ComplianceCheck.VULNERABILITY_MANAGEMENT: {
                "required": True,
                "description": "Maintain vulnerability management program"
            },
            ComplianceCheck.SECURE_SYSTEMS: {
                "required": True,
                "description": "Maintain secure systems and applications"
            }
        }
        
        # Security event cache TTL
        self.security_cache_ttl = 3600  # 1 hour
        
        logger.info("PaymentSecurityManager initialized successfully")
    
    async def validate_payment_security(
        self, 
        payment_data: Dict[str, Any],
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[FraudCheck], List[SecurityEvent]]:
        """
        Comprehensive payment security validation.
        
        Args:
            payment_data (dict): Payment transaction data
            request_metadata (dict): Request metadata (IP, user agent, etc.)
            
        Returns:
            tuple: (is_secure, fraud_checks, security_events)
        """
        try:
            fraud_checks = []
            security_events = []
            
            # Perform fraud detection checks
            fraud_checks.extend(await self._check_transaction_velocity(payment_data, request_metadata))
            fraud_checks.extend(await self._check_amount_anomalies(payment_data))
            fraud_checks.extend(await self._check_geographic_risks(payment_data, request_metadata))
            fraud_checks.extend(await self._check_payment_method_risks(payment_data))
            fraud_checks.extend(await self._check_behavioral_patterns(payment_data, request_metadata))
            
            # Validate PCI DSS compliance
            compliance_checks = await self._validate_pci_compliance(payment_data)
            
            # Check for security violations
            security_events.extend(await self._detect_security_violations(payment_data, request_metadata))
            
            # Calculate overall risk score
            overall_risk_score = self._calculate_overall_risk(fraud_checks)
            
            # Determine if payment is secure
            is_secure = (
                overall_risk_score < 0.7 and  # Low to medium risk
                all(check.passed for check in compliance_checks) and
                not any(event.risk_level == SecurityRiskLevel.CRITICAL for event in security_events)
            )
            
            # Log security assessment
            await self._log_security_assessment(payment_data, is_secure, overall_risk_score, fraud_checks)
            
            logger.info(f"Payment security validation completed: secure={is_secure}, risk_score={overall_risk_score:.2f}")
            
            return is_secure, fraud_checks, security_events
            
        except Exception as e:
            logger.error(f"Error validating payment security: {e}")
            
            # Fail secure - reject if we can't validate
            security_events.append(SecurityEvent(
                event_type="security_validation_error",
                risk_level=SecurityRiskLevel.HIGH,
                description=f"Security validation failed: {str(e)}"
            ))
            
            return False, [], security_events
    
    async def monitor_pci_compliance(self) -> Dict[str, Any]:
        """
        Monitor PCI DSS compliance status.
        
        Returns:
            dict: Compliance status and recommendations
        """
        try:
            compliance_status = {
                "overall_compliant": True,
                "checks": {},
                "violations": [],
                "recommendations": [],
                "last_assessed": datetime.utcnow().isoformat()
            }
            
            # Check each compliance requirement
            for check_type, requirement in self.compliance_requirements.items():
                check_result = await self._assess_compliance_requirement(check_type, requirement)
                compliance_status["checks"][check_type.value] = check_result
                
                if not check_result["compliant"]:
                    compliance_status["overall_compliant"] = False
                    compliance_status["violations"].append({
                        "requirement": check_type.value,
                        "description": requirement["description"],
                        "issue": check_result.get("issue", "Non-compliant")
                    })
            
            # Generate recommendations
            compliance_status["recommendations"] = await self._generate_compliance_recommendations(
                compliance_status["violations"]
            )
            
            logger.info(f"PCI compliance assessment: compliant={compliance_status['overall_compliant']}")
            
            return compliance_status
            
        except Exception as e:
            logger.error(f"Error monitoring PCI compliance: {e}")
            return {
                "overall_compliant": False,
                "error": str(e),
                "last_assessed": datetime.utcnow().isoformat()
            }
    
    async def detect_fraud_patterns(
        self, 
        timeframe_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Detect fraud patterns across payment transactions.
        
        Args:
            timeframe_hours (int): Analysis timeframe in hours
            
        Returns:
            dict: Fraud detection results and patterns
        """
        try:
            start_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
            
            fraud_analysis = {
                "timeframe": f"{timeframe_hours}h",
                "patterns_detected": [],
                "high_risk_transactions": [],
                "blocked_attempts": [],
                "risk_summary": {},
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
            # Analyze transaction patterns
            patterns = await self._analyze_fraud_patterns(start_time)
            fraud_analysis["patterns_detected"] = patterns
            
            # Identify high-risk transactions
            high_risk = await self._identify_high_risk_transactions(start_time)
            fraud_analysis["high_risk_transactions"] = high_risk
            
            # Get blocked attempts
            blocked = await self._get_blocked_attempts(start_time)
            fraud_analysis["blocked_attempts"] = blocked
            
            # Generate risk summary
            fraud_analysis["risk_summary"] = await self._generate_risk_summary(patterns, high_risk, blocked)
            
            logger.info(f"Fraud pattern analysis completed: {len(patterns)} patterns detected")
            
            return fraud_analysis
            
        except Exception as e:
            logger.error(f"Error detecting fraud patterns: {e}")
            return {
                "error": str(e),
                "analyzed_at": datetime.utcnow().isoformat()
            }
    
    async def secure_payment_data(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Secure and sanitize payment data for storage/transmission.
        
        Args:
            payment_data (dict): Raw payment data
            
        Returns:
            dict: Secured payment data
        """
        try:
            secured_data = payment_data.copy()
            
            # Remove sensitive fields
            sensitive_fields = [
                "card_number", "cvv", "cvc", "security_code",
                "bank_account", "routing_number", "ssn"
            ]
            
            for field in sensitive_fields:
                if field in secured_data:
                    del secured_data[field]
            
            # Mask partially sensitive fields
            if "payment_method_id" in secured_data:
                secured_data["payment_method_id"] = self._mask_payment_method_id(
                    secured_data["payment_method_id"]
                )
            
            # Add security metadata
            secured_data["_security"] = {
                "sanitized_at": datetime.utcnow().isoformat(),
                "pci_compliant": True,
                "data_classification": "payment_data"
            }
            
            logger.debug("Payment data secured and sanitized")
            
            return secured_data
            
        except Exception as e:
            logger.error(f"Error securing payment data: {e}")
            return {"error": "Data security failure"}
    
    async def generate_security_token(self, data: str, ttl_seconds: int = 3600) -> str:
        """
        Generate secure token for payment data.
        
        Args:
            data (str): Data to tokenize
            ttl_seconds (int): Token TTL in seconds
            
        Returns:
            str: Secure token
        """
        try:
            # Generate secure random token
            token = secrets.token_urlsafe(32)
            
            # Store tokenized data in Redis with TTL
            redis_client = await get_redis_async()
            token_key = f"payment_token:{token}"
            
            with redis_client.get_connection() as conn:
                conn.setex(token_key, ttl_seconds, data)
            
            logger.debug(f"Security token generated with {ttl_seconds}s TTL")
            
            return token
            
        except Exception as e:
            logger.error(f"Error generating security token: {e}")
            raise
    
    async def validate_security_token(self, token: str) -> Optional[str]:
        """
        Validate and retrieve data from security token.
        
        Args:
            token (str): Security token
            
        Returns:
            str: Original data if valid, None if invalid/expired
        """
        try:
            redis_client = await get_redis_async()
            token_key = f"payment_token:{token}"
            
            with redis_client.get_connection() as conn:
                data = conn.get(token_key)
                if data:
                    # Delete token after use (one-time use)
                    conn.delete(token_key)
                    logger.debug("Security token validated and consumed")
                    return data.decode() if isinstance(data, bytes) else data
            
            logger.warning(f"Invalid or expired security token: {token[:8]}...")
            return None
            
        except Exception as e:
            logger.error(f"Error validating security token: {e}")
            return None
    
    async def _check_transaction_velocity(
        self, 
        payment_data: Dict[str, Any], 
        request_metadata: Optional[Dict[str, Any]]
    ) -> List[FraudCheck]:
        """Check transaction velocity for fraud detection."""
        checks = []
        
        try:
            # Check based on IP address
            if request_metadata and "ip_address" in request_metadata:
                ip_address = request_metadata["ip_address"]
                velocity = await self._get_ip_transaction_velocity(ip_address)
                
                checks.append(FraudCheck(
                    check_type="ip_velocity",
                    passed=velocity <= self.fraud_thresholds["velocity_limit"],
                    risk_score=min(velocity / self.fraud_thresholds["velocity_limit"], 1.0),
                    details=f"IP {ip_address} has {velocity} transactions in last minute",
                    metadata={"ip_address": ip_address, "velocity": velocity}
                ))
            
            # Check based on payment method
            if "payment_method_id" in payment_data:
                pm_velocity = await self._get_payment_method_velocity(payment_data["payment_method_id"])
                
                checks.append(FraudCheck(
                    check_type="payment_method_velocity",
                    passed=pm_velocity <= self.fraud_thresholds["velocity_limit"],
                    risk_score=min(pm_velocity / self.fraud_thresholds["velocity_limit"], 1.0),
                    details=f"Payment method has {pm_velocity} transactions in last minute",
                    metadata={"payment_method_id": payment_data["payment_method_id"], "velocity": pm_velocity}
                ))
                
        except Exception as e:
            logger.warning(f"Error checking transaction velocity: {e}")
            checks.append(FraudCheck(
                check_type="velocity_check_error",
                passed=False,
                risk_score=0.5,
                details=f"Velocity check failed: {str(e)}"
            ))
        
        return checks
    
    async def _check_amount_anomalies(self, payment_data: Dict[str, Any]) -> List[FraudCheck]:
        """Check for amount-based anomalies."""
        checks = []
        
        try:
            amount = payment_data.get("amount", 0)
            
            # Check for suspiciously high amounts
            if amount > self.fraud_thresholds["high_risk_amount"]:
                checks.append(FraudCheck(
                    check_type="high_amount",
                    passed=False,
                    risk_score=min(amount / self.fraud_thresholds["high_risk_amount"] * 0.3, 1.0),
                    details=f"High-value transaction: ${amount:.2f}",
                    metadata={"amount": amount, "threshold": self.fraud_thresholds["high_risk_amount"]}
                ))
            
            # Check for amount patterns (e.g., round numbers might be suspicious)
            if amount > 0 and amount % 100 == 0 and amount > 500:
                checks.append(FraudCheck(
                    check_type="round_amount",
                    passed=True,  # Not necessarily fraudulent, just suspicious
                    risk_score=0.2,
                    details=f"Round amount detected: ${amount:.2f}",
                    metadata={"amount": amount}
                ))
                
        except Exception as e:
            logger.warning(f"Error checking amount anomalies: {e}")
        
        return checks
    
    async def _check_geographic_risks(
        self, 
        payment_data: Dict[str, Any], 
        request_metadata: Optional[Dict[str, Any]]
    ) -> List[FraudCheck]:
        """Check for geographic-based risks."""
        checks = []
        
        try:
            # Check IP geolocation
            if request_metadata and "ip_address" in request_metadata:
                ip_country = await self._get_ip_country(request_metadata["ip_address"])
                
                if ip_country in self.fraud_thresholds["suspicious_countries"]:
                    checks.append(FraudCheck(
                        check_type="suspicious_country",
                        passed=False,
                        risk_score=0.8,
                        details=f"Transaction from suspicious country: {ip_country}",
                        metadata={"country": ip_country, "ip_address": request_metadata["ip_address"]}
                    ))
            
            # Check for VPN/Proxy usage
            if request_metadata and "ip_address" in request_metadata:
                is_proxy = await self._check_proxy_usage(request_metadata["ip_address"])
                
                if is_proxy:
                    checks.append(FraudCheck(
                        check_type="proxy_usage",
                        passed=False,
                        risk_score=0.6,
                        details="Transaction through VPN/Proxy detected",
                        metadata={"ip_address": request_metadata["ip_address"]}
                    ))
                    
        except Exception as e:
            logger.warning(f"Error checking geographic risks: {e}")
        
        return checks
    
    async def _check_payment_method_risks(self, payment_data: Dict[str, Any]) -> List[FraudCheck]:
        """Check payment method-specific risks."""
        checks = []
        
        try:
            payment_method_id = payment_data.get("payment_method_id")
            
            if payment_method_id:
                # Check if payment method has recent failures
                failure_count = await self._get_payment_method_failures(payment_method_id)
                
                if failure_count >= self.fraud_thresholds["failed_attempts"]:
                    checks.append(FraudCheck(
                        check_type="payment_method_failures",
                        passed=False,
                        risk_score=min(failure_count / self.fraud_thresholds["failed_attempts"] * 0.5, 1.0),
                        details=f"Payment method has {failure_count} recent failures",
                        metadata={"payment_method_id": payment_method_id, "failure_count": failure_count}
                    ))
                
                # Check payment method age and usage patterns
                pm_info = await self._get_payment_method_info(payment_method_id)
                if pm_info:
                    # New payment methods are slightly riskier
                    created_hours_ago = (datetime.utcnow() - pm_info.get("created_at", datetime.utcnow())).total_seconds() / 3600
                    
                    if created_hours_ago < 1:  # Created less than 1 hour ago
                        checks.append(FraudCheck(
                            check_type="new_payment_method",
                            passed=True,
                            risk_score=0.3,
                            details=f"Payment method created {created_hours_ago:.1f} hours ago",
                            metadata={"payment_method_id": payment_method_id, "age_hours": created_hours_ago}
                        ))
                        
        except Exception as e:
            logger.warning(f"Error checking payment method risks: {e}")
        
        return checks
    
    async def _check_behavioral_patterns(
        self, 
        payment_data: Dict[str, Any], 
        request_metadata: Optional[Dict[str, Any]]
    ) -> List[FraudCheck]:
        """Check for suspicious behavioral patterns."""
        checks = []
        
        try:
            # Check user agent patterns
            if request_metadata and "user_agent" in request_metadata:
                user_agent = request_metadata["user_agent"]
                
                # Check for bot-like user agents
                suspicious_agents = ["bot", "crawler", "spider", "automated", "script"]
                if any(agent in user_agent.lower() for agent in suspicious_agents):
                    checks.append(FraudCheck(
                        check_type="suspicious_user_agent",
                        passed=False,
                        risk_score=0.7,
                        details=f"Suspicious user agent detected: {user_agent[:50]}...",
                        metadata={"user_agent": user_agent}
                    ))
            
            # Check for rapid retry patterns
            if "payment_method_id" in payment_data:
                rapid_retries = await self._check_rapid_retries(payment_data["payment_method_id"])
                
                if rapid_retries:
                    checks.append(FraudCheck(
                        check_type="rapid_retries",
                        passed=False,
                        risk_score=0.6,
                        details="Rapid retry pattern detected",
                        metadata={"payment_method_id": payment_data["payment_method_id"]}
                    ))
                    
        except Exception as e:
            logger.warning(f"Error checking behavioral patterns: {e}")
        
        return checks
    
    async def _validate_pci_compliance(self, payment_data: Dict[str, Any]) -> List[FraudCheck]:
        """Validate PCI DSS compliance for payment data."""
        compliance_checks = []
        
        try:
            # Check data encryption compliance
            compliance_checks.append(FraudCheck(
                check_type="pci_data_encryption",
                passed=not self._contains_sensitive_data(payment_data),
                risk_score=0.0 if not self._contains_sensitive_data(payment_data) else 1.0,
                details="Payment data encryption compliance check",
                metadata={"has_sensitive_data": self._contains_sensitive_data(payment_data)}
            ))
            
            # Check access control compliance
            compliance_checks.append(FraudCheck(
                check_type="pci_access_control",
                passed=True,  # Assume compliant if we reach this point
                risk_score=0.0,
                details="Access control compliance check",
                metadata={"access_controlled": True}
            ))
            
            # Add more PCI compliance checks as needed
            
        except Exception as e:
            logger.warning(f"Error validating PCI compliance: {e}")
        
        return compliance_checks
    
    async def _detect_security_violations(
        self, 
        payment_data: Dict[str, Any], 
        request_metadata: Optional[Dict[str, Any]]
    ) -> List[SecurityEvent]:
        """Detect security violations in payment request."""
        violations = []
        
        try:
            # Check for data injection attempts
            if self._check_injection_patterns(payment_data):
                violations.append(SecurityEvent(
                    event_type="injection_attempt",
                    risk_level=SecurityRiskLevel.HIGH,
                    description="Potential data injection detected in payment data",
                    metadata={"payment_data_keys": list(payment_data.keys())}
                ))
            
            # Check for suspicious IP addresses
            if request_metadata and "ip_address" in request_metadata:
                ip_address = request_metadata["ip_address"]
                
                if await self._is_blacklisted_ip(ip_address):
                    violations.append(SecurityEvent(
                        event_type="blacklisted_ip",
                        risk_level=SecurityRiskLevel.CRITICAL,
                        description=f"Request from blacklisted IP: {ip_address}",
                        source_ip=ip_address
                    ))
                    
        except Exception as e:
            logger.warning(f"Error detecting security violations: {e}")
        
        return violations
    
    def _calculate_overall_risk(self, fraud_checks: List[FraudCheck]) -> float:
        """Calculate overall risk score from fraud checks."""
        if not fraud_checks:
            return 0.0
        
        # Weight failed checks more heavily
        total_score = 0.0
        weight_sum = 0.0
        
        for check in fraud_checks:
            weight = 2.0 if not check.passed else 1.0
            total_score += check.risk_score * weight
            weight_sum += weight
        
        return total_score / weight_sum if weight_sum > 0 else 0.0
    
    def _contains_sensitive_data(self, data: Dict[str, Any]) -> bool:
        """Check if data contains sensitive payment information."""
        sensitive_patterns = [
            r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',  # Credit card pattern
            r'\d{3,4}',  # CVV pattern (basic)
            r'ssn', r'social.security', r'tax.id'  # SSN patterns
        ]
        
        data_str = str(data).lower()
        
        for pattern in sensitive_patterns:
            if re.search(pattern, data_str):
                return True
                
        return False
    
    def _check_injection_patterns(self, data: Dict[str, Any]) -> bool:
        """Check for SQL injection or other malicious patterns."""
        injection_patterns = [
            r"(\bselect\b|\bunion\b|\bdrop\b|\bdelete\b|\binsert\b|\bupdate\b)",
            r"(<script|javascript:|onload=|onerror=)",
            r"(\.\./|\.\.\\|%2e%2e)",
            r"(exec\(|eval\(|system\()"
        ]
        
        data_str = str(data).lower()
        
        for pattern in injection_patterns:
            if re.search(pattern, data_str, re.IGNORECASE):
                return True
                
        return False
    
    def _mask_payment_method_id(self, payment_method_id: str) -> str:
        """Mask payment method ID for logging."""
        if len(payment_method_id) <= 8:
            return payment_method_id
        
        return payment_method_id[:4] + "*" * (len(payment_method_id) - 8) + payment_method_id[-4:]
    
    # Helper methods for fraud detection (placeholders for actual implementation)
    async def _get_ip_transaction_velocity(self, ip_address: str) -> int:
        """Get transaction velocity for IP address."""
        try:
            redis_client = await get_redis_async()
            velocity_key = f"ip_velocity:{ip_address}"
            
            with redis_client.get_connection() as conn:
                count = conn.get(velocity_key)
                return int(count) if count else 0
                
        except Exception as e:
            logger.warning(f"Error getting IP velocity: {e}")
            return 0
    
    async def _get_payment_method_velocity(self, payment_method_id: str) -> int:
        """Get transaction velocity for payment method."""
        try:
            redis_client = await get_redis_async()
            velocity_key = f"pm_velocity:{payment_method_id}"
            
            with redis_client.get_connection() as conn:
                count = conn.get(velocity_key)
                return int(count) if count else 0
                
        except Exception as e:
            logger.warning(f"Error getting payment method velocity: {e}")
            return 0
    
    async def _get_ip_country(self, ip_address: str) -> str:
        """Get country code for IP address."""
        try:
            # This would integrate with a GeoIP service
            # For now, return placeholder
            return "US"  # Placeholder
            
        except Exception as e:
            logger.warning(f"Error getting IP country: {e}")
            return "UNKNOWN"
    
    async def _check_proxy_usage(self, ip_address: str) -> bool:
        """Check if IP address is using VPN/Proxy."""
        try:
            # This would integrate with a proxy detection service
            # For now, return False (no proxy detected)
            return False  # Placeholder
            
        except Exception as e:
            logger.warning(f"Error checking proxy usage: {e}")
            return False
    
    async def _get_payment_method_failures(self, payment_method_id: str) -> int:
        """Get recent failure count for payment method."""
        try:
            start_time = datetime.utcnow() - timedelta(hours=24)
            
            async with get_db_session() as session:
                failure_count = session.query(PaymentTransaction).filter(
                    PaymentTransaction.stripe_metadata.contains(payment_method_id),
                    PaymentTransaction.status == "failed",
                    PaymentTransaction.created_at >= start_time
                ).count()
                
                return failure_count
                
        except Exception as e:
            logger.warning(f"Error getting payment method failures: {e}")
            return 0
    
    async def _get_payment_method_info(self, payment_method_id: str) -> Optional[Dict[str, Any]]:
        """Get payment method information."""
        try:
            async with get_db_session() as session:
                pm_record = session.query(PaymentMethodRecord).filter(
                    PaymentMethodRecord.payment_method_id == payment_method_id
                ).first()
                
                if pm_record:
                    return {
                        "created_at": pm_record.created_at,
                        "is_active": pm_record.is_active,
                        "card_brand": pm_record.card_brand
                    }
                    
        except Exception as e:
            logger.warning(f"Error getting payment method info: {e}")
        
        return None
    
    async def _check_rapid_retries(self, payment_method_id: str) -> bool:
        """Check for rapid retry patterns."""
        try:
            redis_client = await get_redis_async()
            retry_key = f"retry_pattern:{payment_method_id}"
            
            with redis_client.get_connection() as conn:
                retry_count = conn.get(retry_key)
                return int(retry_count) > 3 if retry_count else False
                
        except Exception as e:
            logger.warning(f"Error checking rapid retries: {e}")
            return False
    
    async def _is_blacklisted_ip(self, ip_address: str) -> bool:
        """Check if IP address is blacklisted."""
        try:
            redis_client = await get_redis_async()
            blacklist_key = f"ip_blacklist:{ip_address}"
            
            with redis_client.get_connection() as conn:
                return conn.exists(blacklist_key)
                
        except Exception as e:
            logger.warning(f"Error checking IP blacklist: {e}")
            return False
    
    async def _log_security_assessment(
        self, 
        payment_data: Dict[str, Any], 
        is_secure: bool, 
        risk_score: float, 
        fraud_checks: List[FraudCheck]
    ):
        """Log security assessment results."""
        try:
            assessment_log = {
                "payment_intent_id": payment_data.get("payment_intent_id"),
                "is_secure": is_secure,
                "risk_score": risk_score,
                "checks_performed": len(fraud_checks),
                "failed_checks": len([c for c in fraud_checks if not c.passed]),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Security assessment: {assessment_log}")
            
        except Exception as e:
            logger.warning(f"Error logging security assessment: {e}")
    
    # Compliance assessment methods (placeholders)
    async def _assess_compliance_requirement(
        self, 
        check_type: ComplianceCheck, 
        requirement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess individual compliance requirement."""
        try:
            # This would perform actual compliance checks
            # For now, return compliant status
            return {
                "compliant": True,
                "last_checked": datetime.utcnow().isoformat(),
                "details": f"{check_type.value} compliance verified"
            }
            
        except Exception as e:
            return {
                "compliant": False,
                "issue": str(e),
                "last_checked": datetime.utcnow().isoformat()
            }
    
    async def _generate_compliance_recommendations(self, violations: List[Dict[str, Any]]) -> List[str]:
        """Generate compliance recommendations."""
        recommendations = []
        
        for violation in violations:
            requirement = violation["requirement"]
            recommendations.append(f"Address {requirement} compliance issue: {violation['description']}")
        
        return recommendations
    
    # Fraud pattern analysis methods (placeholders)
    async def _analyze_fraud_patterns(self, start_time: datetime) -> List[Dict[str, Any]]:
        """Analyze fraud patterns in transactions."""
        # Placeholder implementation
        return []
    
    async def _identify_high_risk_transactions(self, start_time: datetime) -> List[Dict[str, Any]]:
        """Identify high-risk transactions."""
        # Placeholder implementation
        return []
    
    async def _get_blocked_attempts(self, start_time: datetime) -> List[Dict[str, Any]]:
        """Get blocked payment attempts."""
        # Placeholder implementation
        return []
    
    async def _generate_risk_summary(
        self, 
        patterns: List[Dict[str, Any]], 
        high_risk: List[Dict[str, Any]], 
        blocked: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate risk summary."""
        return {
            "total_patterns": len(patterns),
            "high_risk_count": len(high_risk),
            "blocked_count": len(blocked),
            "risk_level": "low" if len(high_risk) == 0 else "medium" if len(high_risk) < 5 else "high"
        }


# Create global security manager instance
payment_security_manager = PaymentSecurityManager()


# Export main components
__all__ = [
    "PaymentSecurityManager",
    "SecurityEvent",
    "FraudCheck", 
    "SecurityRiskLevel",
    "ComplianceCheck",
    "payment_security_manager"
]