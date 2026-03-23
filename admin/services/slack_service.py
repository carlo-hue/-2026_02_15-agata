# agata/admin/services/slack_service.py
"""
Slack Integration Service

Gestisce l'integrazione con Slack:
- Creazione canali per associazioni
- Invio notifiche
- Gestione thread progetti
- Sincronizzazione stato
"""
import os
from typing import Optional, List, Dict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session

from agata.auth_models import Association, SlackChannel, ProjectSlackThread
from agata.admin.services.audit_service import log_audit


class SlackService:
    """Service per gestione Slack"""

    def __init__(self):
        """Inizializza il client Slack"""
        bot_token = os.getenv('SLACK_BOT_TOKEN')
        if not bot_token:
            raise ValueError("SLACK_BOT_TOKEN not configured in environment")

        self.client = WebClient(token=bot_token)
        self.team_id = None  # Caricato al primo utilizzo

    def get_team_id(self) -> str:
        """Ottiene il team_id del workspace"""
        if not self.team_id:
            try:
                response = self.client.auth_test()
                self.team_id = response['team_id']
            except SlackApiError as e:
                raise ValueError(f"Failed to authenticate with Slack: {e.response['error']}")

        return self.team_id

    def create_channel(
        self,
        channel_name: str,
        description: Optional[str] = None,
        is_private: bool = False
    ) -> Dict:
        """
        Crea un nuovo canale Slack

        Args:
            channel_name: Nome del canale (senza #)
            description: Descrizione/topic del canale
            is_private: Se True, crea canale privato

        Returns:
            Dict con info canale creato: {
                'channel_id': str,
                'channel_name': str,
                'created': bool
            }

        Raises:
            SlackApiError: Se la creazione fallisce
        """
        try:
            # Crea il canale
            response = self.client.conversations_create(
                name=channel_name,
                is_private=is_private
            )

            channel_id = response['channel']['id']

            # Imposta topic/descrizione se specificato
            if description:
                self.client.conversations_setTopic(
                    channel=channel_id,
                    topic=description[:250]  # Max 250 caratteri
                )

            return {
                'channel_id': channel_id,
                'channel_name': channel_name,
                'created': True
            }

        except SlackApiError as e:
            # Canale già esistente
            if e.response['error'] == 'name_taken':
                # Cerca il canale esistente
                existing = self.find_channel_by_name(channel_name)
                if existing:
                    return {
                        'channel_id': existing['id'],
                        'channel_name': channel_name,
                        'created': False
                    }

            raise

    def invite_users_to_channel(
        self,
        channel_id: str,
        user_ids: List[str]
    ) -> Dict[str, bool]:
        """
        Invita utenti a un canale

        Args:
            channel_id: ID del canale
            user_ids: Lista di user ID Slack da invitare

        Returns:
            Dict con risultati: {user_id: success}
        """
        results = {}

        for user_id in user_ids:
            try:
                self.client.conversations_invite(
                    channel=channel_id,
                    users=user_id
                )
                results[user_id] = True
            except SlackApiError as e:
                # Ignora errori come "already_in_channel"
                if e.response['error'] == 'already_in_channel':
                    results[user_id] = True
                else:
                    results[user_id] = False

        return results

    def find_channel_by_name(self, channel_name: str) -> Optional[Dict]:
        """
        Cerca un canale per nome

        Args:
            channel_name: Nome del canale (senza #)

        Returns:
            Dict con info canale se trovato, None altrimenti
        """
        try:
            # Lista tutti i canali pubblici
            response = self.client.conversations_list(
                types="public_channel,private_channel",
                limit=1000
            )

            for channel in response['channels']:
                if channel['name'] == channel_name:
                    return channel

            return None

        except SlackApiError:
            return None

    def create_association_channels(
        self,
        db: Session,
        association: Association,
        user_id: str,
        user_email: str
    ) -> List[SlackChannel]:
        """
        Crea tutti i canali Slack per un'associazione

        Crea 3 canali secondo lo schema AGATA:
        - ag-<slug>-coord (coordinamento)
        - ag-<slug>-lavori (analisi available/assigned)
        - ag-<slug>-review (revisione scientifica)

        Args:
            db: Database session
            association: Associazione per cui creare i canali
            user_id: ID utente che esegue l'operazione
            user_email: Email utente che esegue l'operazione

        Returns:
            Lista di SlackChannel creati (vuota se slack_enabled=False)

        Raises:
            SlackApiError: Se la creazione fallisce
        """
        # Controlla se l'integrazione Slack è abilitata per questa associazione
        if not getattr(association, 'slack_enabled', True):
            print(f"[SlackService] Integrazione Slack disabilitata per {association.name}, skip creazione canali")
            return []

        team_id = self.get_team_id()
        created_channels = []

        # Definizione canali da creare
        channel_types = [
            ('coord', 'Coordinamento e discussione generale'),
            ('lavori', 'Analisi progetti disponibili e assegnati'),
            ('review', 'Revisione scientifica progetti')
        ]

        for channel_type, description in channel_types:
            # Genera nome canale
            channel_name = association.get_slack_channel_name(channel_type)

            # Descrizione completa
            full_description = f"{association.name} - {description}"

            try:
                # Crea canale su Slack (PRIVATO)
                result = self.create_channel(
                    channel_name=channel_name,
                    description=full_description,
                    is_private=True  # CANALI PRIVATI
                )

                channel_id = result['channel_id']
                was_created = result['created']

                # Invita utenti default (Giorgio Mazzacurati e Carlo Marino)
                if was_created:
                    default_users = [
                        'U0A773DUFUZ',  # Giorgio Mazzacurati
                        'U0A6S4WC7TQ'   # Carlo Marino
                    ]
                    try:
                        invite_results = self.invite_users_to_channel(
                            channel_id=channel_id,
                            user_ids=default_users
                        )
                        log_audit(
                            user_id=user_id,
                            user_email=user_email,
                            association_id=association.id,
                            action='slack_users_invited',
                            entity_type='slack_channel',
                            entity_id=channel_id,
                            description=f"Invited {sum(invite_results.values())} users to #{channel_name}"
                        )
                    except Exception as e:
                        # Non fallire se l'invito utenti fallisce
                        log_audit(
                            user_id=user_id,
                            user_email=user_email,
                            association_id=association.id,
                            action='slack_users_invite_failed',
                            entity_type='slack_channel',
                            entity_id=channel_id,
                            description=f"Failed to invite users: {str(e)}"
                        )

                # Invia messaggio di benvenuto se il canale è stato appena creato
                if was_created:
                    welcome_message = self._get_welcome_message(association, channel_type)
                    try:
                        self.post_message(
                            channel_id=channel_id,
                            text=welcome_message['text'],
                            blocks=welcome_message.get('blocks')
                        )
                    except SlackApiError as e:
                        # Non fallire se il messaggio di benvenuto fallisce
                        log_audit(
                            user_id=user_id,
                            user_email=user_email,
                            association_id=association.id,
                            action='slack_welcome_message_failed',
                            entity_type='slack_channel',
                            entity_id=channel_id,
                            description=f"Failed to send welcome message: {e.response['error']}"
                        )

                # Verifica se il canale è già associato a questa associazione nel DB
                existing_db_channel = db.query(SlackChannel).filter(
                    SlackChannel.channel_id == channel_id,
                    SlackChannel.association_id == association.id
                ).first()

                if existing_db_channel:
                    # Canale già nel database, salta
                    log_audit(
                        user_id=user_id,
                        user_email=user_email,
                        association_id=association.id,
                        action='slack_channel_already_linked',
                        entity_type='slack_channel',
                        entity_id=channel_id,
                        new_value=channel_name,
                        description=f"Slack channel #{channel_name} already linked to association"
                    )
                    continue

                # Verifica se il canale è già associato a un'altra associazione
                existing_other = db.query(SlackChannel).filter(
                    SlackChannel.channel_id == channel_id,
                    SlackChannel.association_id != association.id
                ).first()

                if existing_other:
                    # Canale già usato da altra associazione - errore
                    log_audit(
                        user_id=user_id,
                        user_email=user_email,
                        association_id=association.id,
                        action='slack_channel_conflict',
                        entity_type='slack_channel',
                        entity_id=channel_id,
                        description=f"Slack channel #{channel_name} already linked to association {existing_other.association_id}"
                    )
                    continue

                # Salva in database
                # created_by può essere None se user_id non è un UUID valido
                created_by_value = user_id if user_id and len(user_id) == 36 else None

                slack_channel = SlackChannel(
                    association_id=association.id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    team_id=team_id,
                    channel_type=channel_type,
                    created_by=created_by_value,
                    is_active=True,
                    settings={
                        'auto_created': True,
                        'description': full_description,
                        'was_created': was_created
                    }
                )

                db.add(slack_channel)
                created_channels.append(slack_channel)

                # Log audit
                log_audit(
                    user_id=user_id,
                    user_email=user_email,
                    association_id=association.id,
                    action='slack_channel_created',
                    entity_type='slack_channel',
                    entity_id=channel_id,
                    new_value=channel_name,
                    description=f"Slack channel #{channel_name} {'created' if was_created else 'linked'}"
                )

            except SlackApiError as e:
                # Log errore ma continua con altri canali
                log_audit(
                    user_id=user_id,
                    user_email=user_email,
                    association_id=association.id,
                    action='slack_channel_creation_failed',
                    entity_type='slack_channel',
                    entity_id=None,
                    description=f"Failed to create #{channel_name}: {e.response['error']}"
                )

        db.commit()
        return created_channels

    def _get_welcome_message(self, association: Association, channel_type: str) -> Dict:
        """
        Genera messaggio di benvenuto per un canale

        Args:
            association: Associazione
            channel_type: Tipo canale ('coord', 'lavori', 'review')

        Returns:
            Dict con 'text' e 'blocks' per il messaggio
        """
        # Testo base per tutti i canali
        base_text = f"Benvenuto nel canale {channel_type} di *{association.name}*!"

        # Contenuto specifico per tipo canale
        if channel_type == 'coord':
            description = "Questo canale è dedicato al coordinamento e alla discussione generale dell'associazione."
            usage = [
                "• Coordinamento attività",
                "• Discussioni generali",
                "• Annunci importanti",
                "• Pianificazione progetti"
            ]
        elif channel_type == 'lavori':
            description = "Questo canale è dedicato all'analisi dei progetti disponibili e assegnati."
            usage = [
                "• Notifiche nuovi progetti",
                "• Discussione assegnazioni",
                "• Aggiornamenti stato analisi",
                "• Richieste supporto tecnico"
            ]
        elif channel_type == 'review':
            description = "Questo canale è dedicato alla revisione scientifica dei progetti completati."
            usage = [
                "• Revisione risultati",
                "• Feedback tecnico-scientifico",
                "• Approvazione per invio AAVSO",
                "• Discussioni metodologiche"
            ]
        else:
            description = "Canale AGATA"
            usage = []

        # Costruisci blocchi Slack
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 Benvenuto in AGATA!",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{association.name}*\n{description}"
                }
            }
        ]

        if usage:
            usage_text = "\n".join(usage)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Utilizzo del canale:*\n{usage_text}"
                }
            })

        blocks.extend([
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "🤖 Canale configurato automaticamente da AGATA Bot"
                    }
                ]
            }
        ])

        return {
            'text': base_text,
            'blocks': blocks
        }

    def post_message(
        self,
        channel_id: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        thread_ts: Optional[str] = None
    ) -> Dict:
        """
        Invia un messaggio a un canale o thread

        Args:
            channel_id: ID del canale Slack
            text: Testo del messaggio (fallback)
            blocks: Blocchi Slack per rich formatting (opzionale)
            thread_ts: Timestamp del thread parent (per rispondere in thread)

        Returns:
            Response da Slack API con ts del messaggio

        Raises:
            SlackApiError: Se l'invio fallisce
        """
        try:
            kwargs = {
                'channel': channel_id,
                'text': text
            }

            if blocks:
                kwargs['blocks'] = blocks

            if thread_ts:
                kwargs['thread_ts'] = thread_ts

            response = self.client.chat_postMessage(**kwargs)
            return response

        except SlackApiError as e:
            raise

    def create_project_thread(
        self,
        db: Session,
        project_id: int,
        channel_id: str,
        message_text: str,
        message_blocks: Optional[List[Dict]] = None
    ) -> ProjectSlackThread:
        """
        Crea un nuovo thread Slack per un progetto

        Args:
            db: Database session
            project_id: ID progetto AGATA
            channel_id: ID canale Slack
            message_text: Testo messaggio iniziale
            message_blocks: Blocchi Slack per rich formatting

        Returns:
            ProjectSlackThread creato

        Raises:
            SlackApiError: Se la creazione fallisce
        """
        # Invia messaggio iniziale
        response = self.post_message(
            channel_id=channel_id,
            text=message_text,
            blocks=message_blocks
        )

        message_ts = response['ts']

        # Crea record in database
        thread = ProjectSlackThread(
            project_id=project_id,
            channel_id=channel_id,
            thread_ts=message_ts,
            message_ts=message_ts,
            slack_type='thread',
            current_state='incoming'  # Verrà aggiornato dal progetto
        )

        db.add(thread)
        db.commit()

        return thread

    def update_thread_message(
        self,
        channel_id: str,
        message_ts: str,
        text: str,
        blocks: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Aggiorna un messaggio esistente

        Args:
            channel_id: ID canale Slack
            message_ts: Timestamp del messaggio da aggiornare
            text: Nuovo testo
            blocks: Nuovi blocchi Slack

        Returns:
            Response da Slack API

        Raises:
            SlackApiError: Se l'aggiornamento fallisce
        """
        try:
            kwargs = {
                'channel': channel_id,
                'ts': message_ts,
                'text': text
            }

            if blocks:
                kwargs['blocks'] = blocks

            response = self.client.chat_update(**kwargs)
            return response

        except SlackApiError as e:
            raise


    def notify_new_project(
        self,
        db: Session,
        project,
        association
    ) -> Optional[ProjectSlackThread]:
        """
        Notifica Slack della creazione di un nuovo progetto.

        Invia un messaggio nel canale 'lavori' dell'associazione
        e crea un ProjectSlackThread per tracciare la conversazione.

        Args:
            db: Database session
            project: Oggetto Project creato
            association: Oggetto Association associata

        Returns:
            ProjectSlackThread creato, o None se fallisce o slack_enabled=False
        """
        # Controlla se l'integrazione Slack è abilitata per questa associazione
        if not getattr(association, 'slack_enabled', True):
            print(f"[SlackService] Integrazione Slack disabilitata per {association.name}, skip notifica nuovo progetto")
            return None

        try:
            # Trova il canale 'lavori' dell'associazione
            lavori_channel = db.query(SlackChannel).filter(
                SlackChannel.association_id == association.id,
                SlackChannel.channel_type == 'lavori',
                SlackChannel.is_active == True
            ).first()

            if not lavori_channel:
                print(f"[SlackService] Canale 'lavori' non trovato per associazione {association.name}")
                return None

            # Costruisci il messaggio
            message_text = f"Nuovo progetto disponibile: *{project.project_code}*"

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"Nuovo Progetto: {project.project_code}",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Titolo:*\n{project.title or 'N/A'}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Gaia ID:*\n`{project.gaia_id}`"
                        }
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Stato:*\n{project.state}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Associazione:*\n{association.name}"
                        }
                    ]
                }
            ]

            # Aggiungi coordinate se disponibili
            if project.ra and project.dec_deg:
                blocks.append({
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*RA:*\n{project.ra:.6f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Dec:*\n{project.dec_deg:.6f}"
                        }
                    ]
                })

            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Il referente può assegnare questo progetto a un analista."
                    }
                ]
            })

            # Crea il thread
            thread = self.create_project_thread(
                db=db,
                project_id=project.id,
                channel_id=lavori_channel.channel_id,
                message_text=message_text,
                message_blocks=blocks
            )

            print(f"[SlackService] Thread creato per progetto {project.project_code} in canale {lavori_channel.channel_name}")
            return thread

        except SlackApiError as e:
            print(f"[SlackService] Errore Slack API: {e.response['error']}")
            return None
        except Exception as e:
            print(f"[SlackService] Errore generico: {e}")
            return None

    def notify_project_assigned(
        self,
        db: Session,
        project,
        analyst,
        assigned_by,
        is_reassignment: bool = False,
        is_self_assignment: bool = False
    ) -> bool:
        """
        Notifica Slack dell'assegnazione di un progetto a un analista.

        Se esiste già un thread per il progetto, risponde in quel thread.
        Altrimenti invia un nuovo messaggio nel canale 'lavori'.

        Args:
            db: Database session
            project: Oggetto Project assegnato
            analyst: Oggetto User a cui è stato assegnato
            assigned_by: Oggetto User che ha assegnato
            is_reassignment: True se è una riassegnazione
            is_self_assignment: True se l'analyst si è auto-assegnato il progetto

        Returns:
            True se la notifica è stata inviata, False altrimenti (anche se slack_enabled=False)
        """
        # Controlla se l'integrazione Slack è abilitata per l'associazione del progetto
        if project.association and not getattr(project.association, 'slack_enabled', True):
            print(f"[SlackService] Integrazione Slack disabilitata per {project.association.name}, skip notifica assegnazione")
            return False

        try:
            # Cerca thread esistente per questo progetto
            existing_thread = db.query(ProjectSlackThread).filter(
                ProjectSlackThread.project_id == project.id,
                ProjectSlackThread.is_active == True
            ).first()

            # Costruisci il messaggio
            analyst_name = analyst.full_name or analyst.name or analyst.email
            assigned_by_name = assigned_by.full_name or assigned_by.name or assigned_by.email if assigned_by else "Sistema"

            if is_self_assignment:
                action_word = "preso in carico"
                action_title = "Progetto Preso in Carico"
                emoji = ":hand:"
                context_text = f"Auto-assegnato da {analyst_name}"
            elif is_reassignment:
                action_word = "riassegnato"
                action_title = "Progetto Riassegnato"
                emoji = ":arrows_counterclockwise:"
                context_text = f"Riassegnato da {assigned_by_name}"
            else:
                action_word = "assegnato"
                action_title = "Progetto Assegnato"
                emoji = ":bust_in_silhouette:"
                context_text = f"Assegnato da {assigned_by_name}"

            message_text = f"Progetto *{project.project_code}* {action_word} {'da' if is_self_assignment else 'a'} {analyst_name}"

            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{action_title}*\n\n"
                                f"Il progetto *{project.project_code}* è stato {action_word} {'da' if is_self_assignment else 'a'} *{analyst_name}*"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": context_text
                        }
                    ]
                }
            ]

            if existing_thread:
                # Rispondi nel thread esistente
                self.client.chat_postMessage(
                    channel=existing_thread.channel_id,
                    thread_ts=existing_thread.thread_ts,
                    text=message_text,
                    blocks=blocks
                )
                print(f"[SlackService] Notifica assegnazione inviata nel thread esistente per {project.project_code}")
            else:
                # Cerca il canale 'lavori' e invia nuovo messaggio
                from agata.auth_models import SlackChannel
                lavori_channel = db.query(SlackChannel).filter(
                    SlackChannel.association_id == project.association_id,
                    SlackChannel.channel_type == 'lavori',
                    SlackChannel.is_active == True
                ).first()

                if lavori_channel:
                    self.post_message(
                        channel_id=lavori_channel.channel_id,
                        text=message_text,
                        blocks=blocks
                    )
                    print(f"[SlackService] Notifica assegnazione inviata nel canale {lavori_channel.channel_name}")
                else:
                    print(f"[SlackService] Canale 'lavori' non trovato per assegnazione {project.project_code}")
                    return False

            return True

        except SlackApiError as e:
            print(f"[SlackService] Errore Slack API assegnazione: {e.response['error']}")
            return False
        except Exception as e:
            print(f"[SlackService] Errore generico assegnazione: {e}")
            return False


# Istanza singleton del servizio
_slack_service = None


def get_slack_service() -> SlackService:
    """
    Ottiene l'istanza singleton del SlackService

    Returns:
        SlackService instance

    Raises:
        ValueError: Se SLACK_BOT_TOKEN non è configurato
    """
    global _slack_service

    if _slack_service is None:
        _slack_service = SlackService()

    return _slack_service
