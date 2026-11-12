"""The test set: real, public businesses, each with the answer a wholesale rep would give.

    expect  "fit":  a US café, bakery or restaurant that serves coffee and doesn't roast it: should score 45+
            "weak": should score under 45, for the reason given
    reason  roaster | chain | abroad   (which deal-breaker should be found)

Labels are my judgment from what these businesses are publicly known for (checked when the snapshot was
recorded). Websites change, so tests run on a saved snapshot of the pages, not the live web.
"""

COMPANIES = [
    # good fits: independent US bakeries, cafés and restaurants
    {"name": "Flour Bakery + Cafe", "website": "https://flourbakery.com", "city": "Boston", "expect": "fit"},
    {"name": "Levain Bakery", "website": "https://levainbakery.com", "city": "New York", "expect": "fit"},
    {"name": "Clinton St. Baking Company", "website": "https://clintonstreetbaking.com", "city": "New York", "expect": "fit"},
    {"name": "Huckleberry Bakery & Cafe", "website": "https://huckleberrycafe.com", "city": "Santa Monica", "expect": "fit"},
    {"name": "Gjusta", "website": "https://gjusta.com", "city": "Los Angeles", "expect": "fit"},
    {"name": "Dahlia Bakery", "website": "https://dahliabakery.com", "city": "Seattle", "expect": "fit"},
    {"name": "Ken's Artisan Bakery", "website": "https://kensartisan.com", "city": "Portland", "expect": "fit"},
    {"name": "Bakery Lorraine", "website": "https://bakerylorraine.com", "city": "San Antonio", "expect": "fit"},
    {"name": "Dominique Ansel Bakery", "website": "https://dominiqueansel.com", "city": "New York", "expect": "fit"},
    {"name": "Zak the Baker", "website": "https://zakthebaker.com", "city": "Miami", "expect": "fit"},
    {"name": "Sullivan Street Bakery", "website": "https://sullivanstreetbakery.com", "city": "New York", "expect": "fit"},
    # roasters: they roast their own coffee
    {"name": "Ritual Coffee Roasters", "website": "https://ritualcoffee.com", "city": "San Francisco", "expect": "weak", "reason": "roaster"},
    {"name": "Blue Bottle Coffee", "website": "https://bluebottlecoffee.com", "city": "Oakland", "expect": "weak", "reason": "roaster"},
    {"name": "Stumptown Coffee Roasters", "website": "https://stumptowncoffee.com", "city": "Portland", "expect": "weak", "reason": "roaster"},
    {"name": "Counter Culture Coffee", "website": "https://counterculturecoffee.com", "city": "Durham", "expect": "weak", "reason": "roaster"},
    {"name": "Intelligentsia Coffee", "website": "https://intelligentsia.com", "city": "Chicago", "expect": "weak", "reason": "roaster"},
    {"name": "Verve Coffee Roasters", "website": "https://vervecoffee.com", "city": "Santa Cruz", "expect": "weak", "reason": "roaster"},
    {"name": "Onyx Coffee Lab", "website": "https://onyxcoffeelab.com", "city": "Rogers, Arkansas", "expect": "weak", "reason": "roaster"},
    # big chains: buy centrally
    {"name": "Starbucks", "website": "https://www.starbucks.com", "city": "", "expect": "weak", "reason": "chain"},
    {"name": "Dunkin'", "website": "https://www.dunkindonuts.com", "city": "", "expect": "weak", "reason": "chain"},
    {"name": "Panera Bread", "website": "https://www.panerabread.com", "city": "", "expect": "weak", "reason": "chain"},
    {"name": "Krispy Kreme", "website": "https://www.krispykreme.com", "city": "", "expect": "weak", "reason": "chain"},
    {"name": "Tim Hortons", "website": "https://www.timhortons.com", "city": "", "expect": "weak", "reason": "chain"},
    # outside the US: Fernwood ships to the US only
    {"name": "Monmouth Coffee", "website": "https://www.monmouthcoffee.co.uk", "city": "London", "expect": "weak", "reason": "abroad"},
    {"name": "Prufrock Coffee", "website": "https://www.prufrockcoffee.com", "city": "London", "expect": "weak", "reason": "abroad"},
    {"name": "Café de Flore", "website": "https://cafedeflore.fr", "city": "Paris", "expect": "weak", "reason": "abroad"},
    {"name": "Lune Croissanterie", "website": "https://lunecroissanterie.com", "city": "Melbourne", "expect": "weak", "reason": "abroad"},
]

# Held out: labelled before any results were seen, and run only after tuning on the list above.
HOLDOUT = [
    {"name": "Republique", "website": "https://republiquela.com", "city": "Los Angeles", "expect": "fit"},
    {"name": "Mah-Ze-Dahr Bakery", "website": "https://mahzedahrbakery.com", "city": "New York", "expect": "fit"},
    {"name": "Breads Bakery", "website": "https://breadsbakery.com", "city": "New York", "expect": "fit"},
    {"name": "Sweet Maple", "website": "https://sweetmaplesf.com", "city": "San Francisco", "expect": "fit"},
    {"name": "Bakery Nouveau", "website": "https://bakerynouveau.com", "city": "Seattle", "expect": "fit"},
    {"name": "Tatte Bakery & Cafe", "website": "https://tattebakery.com", "city": "Boston", "expect": "weak", "reason": "chain"},
    {"name": "Le Pain Quotidien", "website": "https://www.lepainquotidien.com", "city": "", "expect": "weak", "reason": "chain"},
    {"name": "Philz Coffee", "website": "https://philzcoffee.com", "city": "San Francisco", "expect": "weak", "reason": "roaster"},
    {"name": "Heart Coffee Roasters", "website": "https://www.heartroasters.com", "city": "Portland", "expect": "weak", "reason": "roaster"},
    {"name": "Dishoom", "website": "https://www.dishoom.com", "city": "London", "expect": "weak", "reason": "abroad"},
    {"name": "Tim Wendelboe", "website": "https://timwendelboe.no", "city": "Oslo", "expect": "weak", "reason": "abroad"},
]

# which answer shows each deal-breaker
FLAG = {"roaster": ("roasts_own", "yes"), "chain": ("big_chain", "yes"), "abroad": ("in_us", "no")}
