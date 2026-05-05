"""
accounts/management/commands/fix_fund_logs.py

পুরনো activation গুলোর missing inbound FundLog তৈরি করবে।

Run করো:
    python manage.py fix_fund_logs
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from accounts.models import FundLog, GlobalFund

FUND_SHARES = {
    "referral_fund": Decimal("500.00"),
    "matching_fund": Decimal("400.00"),
    "rank_reward_fund": Decimal("500.00"),
    "tour_fund": Decimal("1000.00"),
    "leadership_fund": Decimal("500.00"),
    "company_fund": Decimal("1100.00"),
}


class Command(BaseCommand):
    help = "পুরনো activation এর missing inbound FundLog তৈরি করে"

    def handle(self, *args, **kwargs):
        fund = GlobalFund.objects.first()
        if not fund:
            self.stdout.write(self.style.ERROR("GlobalFund নেই!"))
            return

        self.stdout.write("=" * 50)
        self.stdout.write("Fund Log Fix শুরু হচ্ছে...")
        self.stdout.write("=" * 50)

        for field, share_per_activation in FUND_SHARES.items():
            # এই fund এ এখন পর্যন্ত কত inbound log আছে
            existing_inbound = FundLog.objects.filter(
                fund_type=field,
                transaction_type="inbound",
            ).aggregate(
                total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount")
            )[
                "total"
            ] or Decimal(
                "0"
            )

            # এই fund থেকে কত outbound গেছে
            existing_outbound = FundLog.objects.filter(
                fund_type=field,
                transaction_type="outbound",
            ).aggregate(
                total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount")
            )[
                "total"
            ] or Decimal(
                "0"
            )

            # Current balance থেকে actual total inflow বের করো
            # current_balance = total_inflow - total_outflow
            # তাই total_inflow = current_balance + total_outflow
            current_balance = Decimal(str(getattr(fund, field) or "0.00"))
            actual_total_inflow = current_balance + existing_outbound

            # কত টাকার log missing
            missing_amount = actual_total_inflow - existing_inbound

            self.stdout.write(f"\n{field}:")
            self.stdout.write(f"  Current balance:     {current_balance}")
            self.stdout.write(f"  Existing outbound:   {existing_outbound}")
            self.stdout.write(f"  Actual total inflow: {actual_total_inflow}")
            self.stdout.write(f"  Existing inbound:    {existing_inbound}")
            self.stdout.write(f"  Missing amount:      {missing_amount}")

            if missing_amount > 0:
                # Missing amount এর জন্য একটা correction log তৈরি করো
                FundLog.objects.create(
                    fund_type=field,
                    amount=missing_amount,
                    transaction_type="inbound",
                    reason="Backfill: Historical activation inflow correction",
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✅ {missing_amount} টাকার inbound log তৈরি হয়েছে"
                    )
                )
            elif missing_amount == 0:
                self.stdout.write(self.style.SUCCESS("  ✅ Log already correct"))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠️ Inbound log outbound এর চেয়ে বেশি ({missing_amount}) — skip করা হলো"
                    )
                )

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS("Fix সম্পন্ন! এখন /reports/funds/ check করো।")
        )
        self.stdout.write("=" * 50)
