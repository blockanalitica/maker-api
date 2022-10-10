# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime, timedelta

from discord_webhook import DiscordEmbed, DiscordWebhook
from django.conf import settings
from django.db import connection

from maker.models import RiskPremium
from maker.modules.risk_premium import DEFAULT_SCENARIO_PARAMS
from maker.modules.vaults_at_risk import get_vaults_at_risk
from maker.utils.utils import chunks, format_num
from maker.utils.views import fetch_all


def send_vaults_at_risk_alert():
    data = get_vaults_at_risk()
    if len(data["vaults"]) > 0:

        osm_prices = []
        for osm in data["osm_prices"]:
            osm_prices.append(
                "{}: ${} / ${}".format(
                    osm["symbol"],
                    round(osm["osm_current_price"], 2),
                    round(osm["osm_next_price"], 2),
                )
            )

        webhooks = (
            DiscordWebhook(
                url=settings.DISCORD_ALERT_BOT_WEBHOOK_BA,
                rate_limit_retry=True,
            ),
            DiscordWebhook(
                url=settings.DISCORD_ALERT_BOT_WEBHOOK_MKR,
                rate_limit_retry=True,
            ),
        )
        embed = DiscordEmbed(
            title="Vaults at risk: {}".format(len(data["vaults"])),
            url="https://maker.blockanalitica.com/vaults-at-risk/",
            color="f7051d",
        )

        agg = data["aggregate_data"]
        embed.add_embed_field(
            name="Low risk:",
            value=format_num(round(agg["low"], 2)),
            inline=True,
        )
        embed.add_embed_field(
            name="Medium risk:",
            value=format_num(round(agg["medium"], 2)),
            inline=True,
        )
        embed.add_embed_field(
            name="High risk:",
            value=format_num(round(agg["high"], 2)),
            inline=True,
        )
        embed.add_embed_field(
            name="Total debt:",
            value=format_num(round(agg["total_debt"], 2)),
            inline=True,
        )
        if osm_prices:
            embed.add_embed_field(
                name="OSM prices:",
                value="{}".format("\n".join(osm_prices)),
                inline=False,
            )

        for webhook in webhooks:
            webhook.add_embed(embed)
            request = webhook.execute()
            request.raise_for_status()


def _send_risk_premium_alerts():
    """Checks if risk premium has increased by 2x or more and sends an alert"""
    for ilk in DEFAULT_SCENARIO_PARAMS.keys():
        premiums = list(
            RiskPremium.objects.filter(ilk=ilk)
            .filter(risk_premium__gt=0)
            .order_by("-datetime")
            .values_list("risk_premium", flat=True)[:2]
        )
        if len(premiums) < 2:
            return

        diff = premiums[0] / premiums[1]
        if diff >= 2:
            webhook = DiscordWebhook(
                url=settings.DISCORD_ALERT_BOT_WEBHOOK_BA,
                rate_limit_retry=True,
            )
            embed = DiscordEmbed(
                title="Risk premium for {} has increased by {}x!".format(
                    ilk, round(diff, 2)
                ),
                url="https://maker.blockanalitica.com/simulations/risk-model/?ilk={}".format(
                    ilk
                ),
                color="FF67C5",
            )
            embed.add_embed_field(
                name="New RP:",
                value=str(round(premiums[0], 2)),
                inline=True,
            )
            embed.add_embed_field(
                name="Old RP:",
                value=str(round(premiums[1], 2)),
                inline=True,
            )
            webhook.add_embed(embed)
            request = webhook.execute()
            request.raise_for_status()


def _send_protection_score_alerts():
    """Checks if vaults protection score has changed and sends an alert"""

    # We assume that we're always running this check AFTER the protection score
    # calculation and it's only ran once a day.
    # If protection score is ran multiple times a day, it's gonna compare between the
    # last two records in the databse.

    sql = """
    SELECT
          s.vault_uid
        , s.protection_score
        , v.ilk
    FROM maker_vaultprotectionscore s
    JOIN maker_vault v ON v.uid = s.vault_uid
    WHERE s.datetime::date >= %s
    ORDER BY s.datetime desc
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [(datetime.now() - timedelta(days=1)).date()])
        risk_scores = fetch_all(cursor)

    grouped_scores = defaultdict(list)
    for score in risk_scores:
        grouped_scores[score["vault_uid"]].append(score)

    ilk_messages = defaultdict(list)
    for _, scores in grouped_scores.items():
        if len(scores) < 2:
            continue

        if scores[0]["protection_score"] != scores[1]["protection_score"]:
            ilk_messages[scores[0]["ilk"]].append(
                "{} {} -> {}".format(
                    scores[0]["vault_uid"],
                    scores[1]["protection_score"],
                    scores[0]["protection_score"],
                )
            )

    for ilk, messages in ilk_messages.items():
        for msgs in chunks(messages[:20], 25):
            webhook = DiscordWebhook(
                url=settings.DISCORD_ALERT_BOT_WEBHOOK_BA, rate_limit_retry=True
            )
            embed = DiscordEmbed(
                title="Vault Protection Score Changes for {}".format(ilk),
                url="https://maker.blockanalitica.com/vaults/{}/".format(ilk),
                color="ffff00",
            )
            embed.add_embed_field(name="Vaults", value="{}".format("\n".join(msgs)))
            webhook.add_embed(embed)
            request = webhook.execute()
            request.raise_for_status()


def send_risk_premium_and_protection_score_alerts():
    _send_risk_premium_alerts()
    _send_protection_score_alerts()
