__name__ = "delete"
__summary__ = "Delete one or more tokens for a given user"
__description__ = "Delete one or more tokens for a given user"


import sys

import rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import valid_email


def confirm_token_deletion() -> bool:
    """Prompts the user to confirm token deletion.

    Returns True only if the user explicitly responds with 'y' or 'yes'.
    """
    try:
        # Prompt the user for input
        response = input(
            "Are you sure you want to delete the specified token(s)? y/N: "
        )

        # Clean up whitespace and normalize to lowercase
        cleaned_response = response.strip().lower()

        # Return True ONLY on an explicit affirmative answer
        return cleaned_response in ("y", "yes")

    except (KeyboardInterrupt, EOFError):
        # Gracefully handle Ctrl+C or Ctrl+D by defaulting to False
        print("\nOperation cancelled.")
        return False


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
        "-t",
        "--token-id",
        action="append",
        type=str,
        help="One or more tokens that are to be deleted.",
    )


def exec(args):

    from locutus.model.api_token import ApiToken
    from locutus.model.user import User

    token_ids = set(args.token_id)
    # Initialize the model's database client
    console = Console()

    if not confirm_token_deletion():
        Console(stderr=True).print.write("User chose not to continue with deletion.")
        sys.exit(1)
    if args.email_address != "admin":
        user = User.find_by_email(args.email_address)
        if user:
            table = Table(
                title="Token Details",
                show_header=True,
                header_style="bold magenta",
                box=rich.box.SIMPLE,
            )
            table.add_column("Token ID", style="dim", width=30)
            table.add_column("Token Status", style="dim", width=10)
            table.add_column("Token Name", style="dim", width=12)
            table.add_column("Expires At", style="dim", width=20)

            tokens = ApiToken.list_for_user(user.id)
            for token in tokens:
                if token.id in token_ids or "all" in token_ids:
                    ApiToken.delete(token.id, user.id)
                    table.add_row(
                        token.id,
                        "🟥",
                        token.name,
                        token.expires_at.isoformat(),
                    )
                else:
                    table.add_row(
                        token.id,
                        "✅",
                        token.name,
                        token.expires_at.isoformat(),
                    )

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
