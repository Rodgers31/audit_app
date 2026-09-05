#!/usr/bin/env python3
"""Add governor names from official Council of Governors (cog.go.ke) to enhanced_county_data.json"""
import json

# Source: https://cog.go.ke/current-governors/ (2022-2027 term)
GOVERNORS = {
    "Mombasa": "Abdulswamad Shariff Nassir",
    "Kwale": "Fatuma Mohamed Achani",
    "Kilifi": "Gideon Maitha Mung'aro",
    "Tana River": "Dhadho Gaddae Godhana",
    "Lamu": "Issa Abdalla Timamy",
    "Taita Taveta": "Andrew Mwadime",
    "Garissa": "Nathif Adam Jama",
    "Wajir": "Ahmed Abdullahi",
    "Mandera": "Mohamed Adan Khalif",
    "Marsabit": "Mohamud Mohamed Ali",
    "Isiolo": "Abdi Ibrahim Hassan",
    "Meru": "Isaac Mutuma M'ethingia",
    "Tharaka Nithi": "Muthomi Njuki",
    "Embu": "Cecily Mutitu Mbarire",
    "Kitui": "Julius Makau Malombe",
    "Machakos": "Wavinya Ndeti",
    "Makueni": "Mutula Kilonzo Jr.",
    "Nyandarua": "Moses Ndirangu Kiarie Badilisha",
    "Nyeri": "Mutahi Kahiga",
    "Kirinyaga": "Anne Mumbi Waiguru",
    "Murang'a": "Irungu Kangata",
    "Kiambu": "Paul Kimani Wamatangi",
    "Turkana": "Jeremiah Ekamais Lomorukai",
    "West Pokot": "Simon Kachapin Kitalei",
    "Samburu": "Jonathan Lelelit Lati",
    "Trans Nzoia": "George Natembeya",
    "Uasin Gishu": "Jonathan Bii",
    "Elgeyo Marakwet": "Wisley Rotich",
    "Nandi": "Stephen Kipyego Sang",
    "Baringo": "Benjamin Chesire Cheboi",
    "Laikipia": "Joshua Wakahora Irungu",
    "Nakuru": "Susan Wakarura Kihika",
    "Narok": "Patrick Keturet Ole Ntutu",
    "Kajiado": "Joseph Jama Ole Lenku",
    "Kericho": "Erick Kipkoech Mutai",
    "Bomet": "Hillary K. Barchok",
    "Kakamega": "Fernandes Barasa",
    "Vihiga": "Wilber Khasilwa Ottichilo",
    "Bungoma": "Kenneth Makelo Lusaka",
    "Busia": "Paul Nyongesa Otuoma",
    "Siaya": "James Orengo",
    "Kisumu": "Peter Anyang' Nyong'o",
    "Homa Bay": "Gladys Atieno Nyasuna Wanga",
    "Migori": "George Ochilo Ayacko",
    "Kisii": "Simba Arati",
    "Nyamira": "Amos Kimwomi Nyaribo",
    "Nairobi": "Sakaja Arthur Johnson",
}

with open("backend/data/reference/enhanced_county_data.json", "r") as f:
    data = json.load(f)

for county_name, county_info in data["county_data"].items():
    if county_name in GOVERNORS:
        county_info["governor"] = GOVERNORS[county_name]
    else:
        print(f"WARNING: No governor for {county_name}")

matched = sum(1 for c in data["county_data"] if "governor" in data["county_data"][c])
print(f"Added governor to {matched}/47 counties")

with open("backend/data/reference/enhanced_county_data.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Done - enhanced_county_data.json updated")
