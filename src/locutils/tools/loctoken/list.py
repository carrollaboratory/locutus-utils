__name__ = "list"
__summary__ = "List all available tokens for an active user"
__description__ = "List all available tokens for an active user"


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


def exec(args):

    from locutus.model.api_token import ApiToken
    from locutus.model.user import User

    # Initialize the model's database client
    console = Console()

    user = User.find_by_email(args.email_address)
    if user:
        table = Table(
            title="Token Details",
            show_header=True,
            header_style="bold magenta",
            box=rich.box.SIMPLE,
        )
        table.add_column("Token ID", style="dim", width=30)
        table.add_column("Token Name", style="dim", width=20)
        table.add_column("Expires At", style="dim", width=20)

        tokens = ApiToken.list_for_user(user.id)
        for token in tokens:
            table.add_row(token.id, token.name, token.expires_at.isoformat())

        console.print(table)

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
