"""
Authentication and authorization module for dashboard API.
Provides JWT token validation, role-based access control, and security middleware.
"""

import logging
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel

from ..config.settings import settings
from ..config.logging_config import get_logger

# Configure logging
logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security dependency
security = HTTPBearer()


class UserRole(Enum):
    """User roles for role-based access control."""
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"
    API = "api"
    GUEST = "guest"


class Permission(Enum):
    """System permissions for fine-grained access control."""
    READ_ORDERS = "read:orders"
    WRITE_ORDERS = "write:orders"
    DELETE_ORDERS = "delete:orders"
    READ_ANALYTICS = "read:analytics"
    READ_SYSTEM = "read:system"
    WRITE_SYSTEM = "write:system"
    MANAGE_USERS = "manage:users"
    MANAGE_SETTINGS = "manage:settings"


# Role-permission mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        Permission.READ_ORDERS,
        Permission.WRITE_ORDERS,
        Permission.DELETE_ORDERS,
        Permission.READ_ANALYTICS,
        Permission.READ_SYSTEM,
        Permission.WRITE_SYSTEM,
        Permission.MANAGE_USERS,
        Permission.MANAGE_SETTINGS,
    ],
    UserRole.MANAGER: [
        Permission.READ_ORDERS,
        Permission.WRITE_ORDERS,
        Permission.READ_ANALYTICS,
        Permission.READ_SYSTEM,
        Permission.MANAGE_SETTINGS,
    ],
    UserRole.STAFF: [
        Permission.READ_ORDERS,
        Permission.WRITE_ORDERS,
        Permission.READ_ANALYTICS,
    ],
    UserRole.API: [
        Permission.READ_ORDERS,
        Permission.WRITE_ORDERS,
        Permission.READ_ANALYTICS,
    ],
    UserRole.GUEST: [
        Permission.READ_ORDERS,
    ],
}


class User(BaseModel):
    """User model for authentication."""
    user_id: str
    username: str
    role: UserRole
    permissions: List[Permission]
    email: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True


class TokenData(BaseModel):
    """JWT token data model."""
    user_id: str
    username: str
    role: str
    permissions: List[str]
    exp: datetime
    iat: datetime


class AuthError(Exception):
    """Custom authentication error."""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthManager:
    """
    Authentication and authorization manager.
    Handles JWT tokens, user validation, and permission checking.
    """
    
    def __init__(self):
        self.secret_key = settings.secret_key or "your-secret-key-change-in-production"
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60 * 24  # 24 hours
        
        # In-memory user store (replace with database in production)
        self.users = self._initialize_default_users()
        
        logger.info("AuthManager initialized")
    
    def _initialize_default_users(self) -> Dict[str, User]:
        """Initialize default users for development."""
        default_users = {}
        
        # Admin user
        admin_user = User(
            user_id="admin-001",
            username="admin",
            role=UserRole.ADMIN,
            permissions=ROLE_PERMISSIONS[UserRole.ADMIN],
            email="admin@pizzarestaurant.com",
            created_at=datetime.utcnow(),
            is_active=True
        )
        default_users["admin"] = admin_user
        
        # Manager user
        manager_user = User(
            user_id="manager-001",
            username="manager",
            role=UserRole.MANAGER,
            permissions=ROLE_PERMISSIONS[UserRole.MANAGER],
            email="manager@pizzarestaurant.com",
            created_at=datetime.utcnow(),
            is_active=True
        )
        default_users["manager"] = manager_user
        
        # Staff user
        staff_user = User(
            user_id="staff-001",
            username="staff",
            role=UserRole.STAFF,
            permissions=ROLE_PERMISSIONS[UserRole.STAFF],
            email="staff@pizzarestaurant.com",
            created_at=datetime.utcnow(),
            is_active=True
        )
        default_users["staff"] = staff_user
        
        # API user
        api_user = User(
            user_id="api-001",
            username="api",
            role=UserRole.API,
            permissions=ROLE_PERMISSIONS[UserRole.API],
            created_at=datetime.utcnow(),
            is_active=True
        )
        default_users["api"] = api_user
        
        return default_users
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        try:
            # For development, use simple password validation
            if username in self.users:
                user = self.users[username]
                
                # Simple password check for development
                if password == "password" or password == f"{username}-password":
                    user.last_login = datetime.utcnow()
                    return user
            
            return None
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
    
    def create_access_token(self, user: User) -> str:
        """
        Create JWT access token for user.
        
        Args:
            user: User object
            
        Returns:
            JWT token string
        """
        try:
            expires_delta = timedelta(minutes=self.access_token_expire_minutes)
            expire = datetime.utcnow() + expires_delta
            
            payload = {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role.value,
                "permissions": [p.value for p in user.permissions],
                "exp": expire,
                "iat": datetime.utcnow(),
                "iss": "pizza-dashboard",
                "sub": user.user_id
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            
            logger.info(f"Access token created for user {user.username}")
            return token
            
        except Exception as e:
            logger.error(f"Error creating access token: {str(e)}")
            raise AuthError("Failed to create access token")
    
    def verify_token(self, token: str) -> TokenData:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            TokenData object
            
        Raises:
            AuthError: If token is invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Extract token data
            token_data = TokenData(
                user_id=payload.get("user_id"),
                username=payload.get("username"),
                role=payload.get("role"),
                permissions=payload.get("permissions", []),
                exp=datetime.fromtimestamp(payload.get("exp")),
                iat=datetime.fromtimestamp(payload.get("iat"))
            )
            
            # Check expiration
            if token_data.exp < datetime.utcnow():
                raise AuthError("Token has expired")
            
            return token_data
            
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token")
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            raise AuthError("Token verification failed")
    
    def get_user_by_token(self, token: str) -> User:
        """
        Get user object from JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            User object
            
        Raises:
            AuthError: If token is invalid or user not found
        """
        try:
            token_data = self.verify_token(token)
            
            # Get user from store
            if token_data.username in self.users:
                user = self.users[token_data.username]
                if user.is_active:
                    return user
                else:
                    raise AuthError("User account is disabled")
            else:
                raise AuthError("User not found")
                
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Error getting user by token: {str(e)}")
            raise AuthError("Failed to get user from token")
    
    def check_permission(self, user: User, required_permission: Permission) -> bool:
        """
        Check if user has required permission.
        
        Args:
            user: User object
            required_permission: Required permission
            
        Returns:
            True if user has permission, False otherwise
        """
        return required_permission in user.permissions
    
    def check_role(self, user: User, required_roles: List[UserRole]) -> bool:
        """
        Check if user has one of the required roles.
        
        Args:
            user: User object
            required_roles: List of acceptable roles
            
        Returns:
            True if user has required role, False otherwise
        """
        return user.role in required_roles
    
    def create_api_key(self, user_id: str, name: str = "API Key") -> str:
        """
        Create API key for programmatic access.
        
        Args:
            user_id: User identifier
            name: API key name/description
            
        Returns:
            API key string
        """
        try:
            # Generate secure API key
            key_data = f"{user_id}:{name}:{datetime.utcnow().isoformat()}:{secrets.token_hex(16)}"
            api_key = hashlib.sha256(key_data.encode()).hexdigest()
            
            logger.info(f"API key created for user {user_id}: {name}")
            return f"pk_live_{api_key[:32]}"
            
        except Exception as e:
            logger.error(f"Error creating API key: {str(e)}")
            raise AuthError("Failed to create API key")


# Global auth manager instance
auth_manager = AuthManager()


# Authentication dependencies

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current authenticated user.
    
    Args:
        credentials: HTTP Bearer token
        
    Returns:
        User object
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        token = credentials.credentials
        
        # Handle development tokens
        if settings.environment == "development":
            if token == "dashboard-dev-token":
                return auth_manager.users["admin"]
            elif token.startswith("dev-"):
                return auth_manager.users.get("staff", auth_manager.users["admin"])
        
        # Handle API keys
        if token.startswith("pk_live_"):
            # Simple API key validation for development
            return auth_manager.users["api"]
        
        # JWT token validation
        user = auth_manager.get_user_by_token(token)
        return user
        
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure user has admin role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_manager_or_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure user has manager or admin role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user is not manager or admin
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or admin access required"
        )
    return current_user


def require_permission(permission: Permission):
    """
    Decorator factory to require specific permission.
    
    Args:
        permission: Required permission
        
    Returns:
        Dependency function
    """
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not auth_manager.check_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission.value}"
            )
        return current_user
    
    return permission_checker


def require_role(roles: List[UserRole]):
    """
    Decorator factory to require specific roles.
    
    Args:
        roles: List of acceptable roles
        
    Returns:
        Dependency function
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not auth_manager.check_role(current_user, roles):
            role_names = [role.value for role in roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles required: {', '.join(role_names)}"
            )
        return current_user
    
    return role_checker


# Rate limiting (simple implementation)
class RateLimiter:
    """Simple rate limiter for API endpoints."""
    
    def __init__(self):
        self.requests = {}  # {user_id: [(timestamp, count), ...]}
        self.limits = {
            UserRole.ADMIN: (1000, 3600),  # 1000 requests per hour
            UserRole.MANAGER: (500, 3600),  # 500 requests per hour
            UserRole.STAFF: (200, 3600),   # 200 requests per hour
            UserRole.API: (2000, 3600),    # 2000 requests per hour
            UserRole.GUEST: (50, 3600),    # 50 requests per hour
        }
    
    def is_allowed(self, user: User) -> bool:
        """
        Check if user is within rate limits.
        
        Args:
            user: User object
            
        Returns:
            True if request is allowed, False otherwise
        """
        try:
            current_time = datetime.utcnow()
            user_id = user.user_id
            
            # Get rate limit for user role
            limit, window = self.limits.get(user.role, (100, 3600))
            
            # Clean old requests
            if user_id in self.requests:
                cutoff_time = current_time - timedelta(seconds=window)
                self.requests[user_id] = [
                    (timestamp, count) for timestamp, count in self.requests[user_id]
                    if timestamp > cutoff_time
                ]
            else:
                self.requests[user_id] = []
            
            # Count current requests
            current_count = sum(count for _, count in self.requests[user_id])
            
            # Check limit
            if current_count >= limit:
                return False
            
            # Add current request
            self.requests[user_id].append((current_time, 1))
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            return True  # Allow on error


# Global rate limiter
rate_limiter = RateLimiter()


async def check_rate_limit(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to check rate limits.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User object
        
    Raises:
        HTTPException: If rate limit exceeded
    """
    if not rate_limiter.is_allowed(current_user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )
    return current_user


# Export main components
__all__ = [
    "auth_manager",
    "get_current_user",
    "get_admin_user",
    "get_manager_or_admin_user",
    "require_permission",
    "require_role",
    "check_rate_limit",
    "User",
    "UserRole",
    "Permission",
    "AuthError",
    "rate_limiter"
]