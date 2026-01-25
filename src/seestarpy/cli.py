import sys
import click
from seestarpy import raw


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """
    Seestar scope control CLI
    """
    if ctx.invoked_subcommand is None:
        legacy_dispatch()


# ---------- Modern commands ----------

@cli.command()
def open():
    """Move scope to horizon"""
    result = raw.scope_move_to_horizon()
    click.echo(result.get("result"))


@cli.command()
@click.option("--eq/--no-eq", default=True, help="Enable EQ mode")
def close(eq):
    """Park scope"""
    result = raw.scope_park(eq)
    click.echo(result.get("result"))


@cli.command()
@click.argument("ra")
@click.argument("dec")
@click.option("--name", default="BogaNyet")
@click.option("--filter", "filter_name", default=False)
def goto(ra, dec, name, filter_name):
    """Go to RA/DEC"""
    result = raw.iscope_start_view(ra, dec, name, filter_name)
    click.echo(result.get("result"))


@cli.command(name="filter")
@click.argument("position", required=False, type=int)
def filter_cmd(position):
    """Get or set filter wheel position"""
    if position is not None:
        raw.set_wheel_position(position)
    result = raw.get_wheel_position()
    click.echo(result.get("result"))


@cli.command()
@click.argument("seconds", required=False, type=int)
def exp(seconds):
    """Get or set exposure time (seconds)"""
    if seconds is not None:
        raw.set_setting(exp_ms={"stack_l": seconds * 1000})
    result = raw.get_setting()
    click.echo(result.get("result"))


@cli.command()
def location():
    """Sync and show system time/location"""
    raw.pi_set_time()
    result = raw.pi_get_time()
    click.echo(result.get("result"))


# ---------- Legacy argv compatibility ----------

def legacy_dispatch():
    argv = sys.argv

    if len(argv) < 2:
        click.echo(cli.get_help(click.Context(cli)))
        sys.exit(0)

    cmd = argv[1]

    if cmd.startswith("op"):
        result = raw.scope_move_to_horizon()

    elif cmd.startswith("cl"):
        eq = bool(argv[2]) if len(argv) > 2 else True
        result = raw.scope_park(eq)

    elif cmd.startswith("go"):
        ra, dec = argv[2], argv[3]
        name = argv[4] if len(argv) > 4 else "BogaNyet"
        filter_name = argv[5] if len(argv) > 5 else False
        result = raw.iscope_start_view(ra, dec, name, filter_name)

    elif cmd.startswith("fil"):
        if len(argv) > 2:
            raw.set_wheel_position(int(argv[2]))
        result = raw.get_wheel_position()

    elif cmd.startswith("exp"):
        if len(argv) > 2:
            raw.set_setting(exp_ms={"stack_l": int(float(argv[2])) * 1000})
        result = raw.get_setting()

    elif cmd.startswith("loc"):
        raw.pi_set_time()
        result = raw.pi_get_time()

    else:
        raise click.ClickException(f"Unknown command: {cmd}")

    click.echo(result.get("result"))


def main():
    cli(prog_name="seestar")


if __name__ == "__main__":
    main()
