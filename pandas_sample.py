import pandas as pd

# Create a sample DataFrame
data = {
    "Name":   ["Alice", "Bob", "Charlie", "Diana", "Eve"],
    "Age":    [25, 30, 35, 28, 22],
    "City":   ["New York", "London", "Paris", "Tokyo", "Sydney"],
    "Salary": [70000, 85000, 90000, 78000, 62000],
}

df = pd.DataFrame(data)

print("=== Full DataFrame ===")
print(df)

print("\n=== Basic Stats ===")
print(df[["Age", "Salary"]].describe())

print("\n=== Filter: Age > 25 ===")
print(df[df["Age"] > 25])

print("\n=== Sorted by Salary (desc) ===")
print(df.sort_values("Salary", ascending=False))

print("\n=== Average Salary ===")
print(f"${df['Salary'].mean():,.0f}")

# Add a new column
df["Senior"] = df["Age"] >= 30
print("\n=== With 'Senior' Column ===")
print(df)
