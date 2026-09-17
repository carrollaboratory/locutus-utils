__name__ = "create"
__summary__ = "Create an API token for an active user"
__description__ = "Create an API token for an active user"


from datetime import datetime

import rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import valid_email


def add_arguments(subparsers):
    local_parser = subparsers.add_parser(
        __name__, help=__summary__, description=__description__
    )

    local_parser.add_argument(
        "-e",
        "--email-address",
        required=True,
        type=valid_email,
        help="Email address associated with the account to generate a token for.",
    )
    local_parser.add_argument(
        "-n",
        "--token-name",
        required=True,
        help="Name that appears in MapDragon for the user to review",
    )
    local_parser.add_argument(
        "-ex",
        "--expiration-date",
        type=datetime.fromisoformat,
        default=datetime.today().replace(year=datetime.today().year + 1),
        help="The target date in YYYY-MM-DD format (default: 1 year from today)",
    )


def exec(args):

    from locutus.model.api_token import ApiToken
    from locutus.model.user import User

    # Initialize the model's database client
    console = Console()

    user = User.find_by_email(args.email_address)
    if user:
        token_details, token = ApiToken.create(
            user_id=user.id, name=args.token_name, expires_at=args.expiration_date
        )

        table = Table(
            title="User Details",
            show_header=True,
            header_style="bold magenta",
            box=rich.box.SIMPLE,
        )
        table.add_column("Setting", style="dim", width=20)
        table.add_column("Value", style="cyan")

        table.add_row("TOKEN", f"[green]{token}[/green]")
        table.add_row("User ID", token_details.user_id)
        table.add_row("Token Name", token_details.name)
        table.add_row("Expires At", token_details.expires_at.isoformat())

        console.print(table)

        warning_message = (
            "[bold red]⚠️  IMPORTANT SECURITY WARNING[/bold red]\n\n"
            "Make sure to copy your this token now. "
            "[bold white]You will not be able to see it again.[/bold white]\n"
            "You are responsible for safely storing this token (e.g., in a password manager)."
        )

        console.print(
            Panel(warning_message, border_style="red", expand=False, padding=(1, 2))
        )
    else:
        console.print(
            Panel(
                f"[bold red]❌ Account Not Found[/bold red]\n\n"
                f"The email address [yellow]'{args.email_address}'[/yellow] is not currently associated with an active account.\n"
                "If the email has been granted access to an institution, it could be that they have never logged in and simply don't have an active account."
                "Please check the spelling or ensure the user has been provisioned in the database.",
                border_style="red",
                title="Lookup Error",
                title_align="left",
            )
        )
