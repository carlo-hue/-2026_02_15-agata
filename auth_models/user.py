# agata/auth_models/user.py
"""
User model - Utenti AGATA con autenticazione OAuth
Implementa Flask-Login UserMixin per integrazione
"""
from sqlalchemy import String, Boolean, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from flask_login import UserMixin
from agata.models import Base


class User(Base, UserMixin):
    """
    Utente AGATA con autenticazione OAuth 2.0

    Supporta multi-provider (Google, Slack, GitHub)
    Compatibile con Flask-Login per gestione sessioni
    """
    __tablename__ = "agata_users"

    # Primary key (UUID)
    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    comment="UUID")

    # Dati personali
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False,
                                       comment="Email univoca utente")
    name: Mapped[str | None] = mapped_column(String(255), nullable=True,
                                             comment="Nome")
    surname: Mapped[str | None] = mapped_column(String(255), nullable=True,
                                                 comment="Cognome")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True,
                                                    comment="URL immagine profilo (da OAuth provider)")

    # Autenticazione OAuth
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True,
                                                  comment="Provider OAuth: google, slack, github")
    provider_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True,
                                                          comment="ID utente nel provider OAuth")
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False,
                                              comment="TRUE se email @astrogen.it")

    # Associazione e ruolo
    association_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agata_associations.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID associazione di appartenenza (NULL per superuser)"
    )
    role: Mapped[str] = mapped_column(
        SQLEnum('superuser', 'admin', 'reviewer', 'analyst', 'viewer', name='user_role'),
        default='analyst',
        comment="superuser: bacino centrale | admin: gestione associazione | reviewer: revisione scientifica | analyst: analisi stelle | viewer: sola lettura"
    )

    # Stato account
    is_active: Mapped[bool] = mapped_column(Boolean, default=True,
                                            comment="Account attivo")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False,
                                                  comment="Email verificata")

    # Audit
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(nullable=True,
                                                         comment="Ultimo accesso")
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True,
                                                       comment="IP ultimo accesso")

    # Relationships
    association: Mapped["Association"] = relationship("Association", back_populates="users")
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship("OAuthToken", back_populates="user",
                                                             cascade="all, delete-orphan")
    assigned_projects: Mapped[list["Project"]] = relationship(
        "Project",
        foreign_keys="[Project.assigned_to]",
        back_populates="assigned_user"
    )
    reviewed_projects: Mapped[list["Project"]] = relationship(
        "Project",
        foreign_keys="[Project.reviewed_by]",
        back_populates="reviewer"
    )

    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}', role='{self.role}')>"

    # Flask-Login required methods
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.id)

    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True

    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False

    # Utility properties
    @property
    def full_name(self) -> str:
        """Nome completo utente"""
        if self.name and self.surname:
            return f"{self.name} {self.surname}"
        return self.name or self.email

    @property
    def is_superuser(self) -> bool:
        """Check se utente è superuser"""
        return self.role == 'superuser'

    @property
    def is_admin(self) -> bool:
        """Check se utente è admin (o superiore)"""
        return self.role in ('superuser', 'admin')

    @property
    def is_reviewer(self) -> bool:
        """Check se utente è reviewer (o superiore)"""
        return self.role in ('superuser', 'admin', 'reviewer')

    @property
    def is_analyst(self) -> bool:
        """Check se utente è analyst (o superiore)"""
        return self.role in ('superuser', 'admin', 'reviewer', 'analyst')

    def has_permission(self, permission: str) -> bool:
        """
        Verifica se l'utente ha un determinato permesso

        Gerarchia permessi:
        superuser > admin > reviewer > analyst > viewer

        Args:
            permission: 'read', 'write', 'analyze', 'review', 'admin', 'superuser'

        Returns:
            True se l'utente ha il permesso
        """
        permission_hierarchy = {
            'superuser': ['read', 'write', 'analyze', 'review', 'admin', 'superuser'],
            'admin': ['read', 'write', 'analyze', 'review', 'admin'],
            'reviewer': ['read', 'write', 'analyze', 'review'],
            'analyst': ['read', 'write', 'analyze'],
            'viewer': ['read'],
        }

        user_permissions = permission_hierarchy.get(self.role, [])
        return permission in user_permissions

    def can_access_project(self, project: "Project") -> bool:
        """
        Verifica se l'utente può accedere a un progetto

        Rules:
        - Superuser: accede a tutto
        - Altri: solo progetti della propria associazione

        Args:
            project: Istanza Project

        Returns:
            True se può accedere
        """
        if self.is_superuser:
            return True

        return project.association_id == self.association_id

    def can_assign_project(self, project: "Project") -> bool:
        """
        Verifica se l'utente può auto-assegnarsi un progetto

        Rules:
        - Progetto deve essere in stato 'available'
        - Utente deve essere analyst, reviewer o admin
        - Progetto deve appartenere alla stessa associazione

        Args:
            project: Istanza Project

        Returns:
            True se può assegnare
        """
        if not self.can_access_project(project):
            return False

        if project.state != 'available':
            return False

        return self.role in ('analyst', 'reviewer', 'admin')
