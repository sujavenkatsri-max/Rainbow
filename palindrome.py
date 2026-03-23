def is_palindrome(s):
    """
    Check if a string is a palindrome.
    Ignores spaces and case sensitivity.
    """
    # Remove spaces and convert to lowercase
    cleaned = s.replace(" ", "").lower()
    
    # Compare string with its reverse
    return cleaned == cleaned[::-1]


# Get user input
user_input = input("Enter a string to check if it's a palindrome: ")

# Check and display result
if is_palindrome(user_input):
    print(f"'{user_input}' is a palindrome!")
else:
    print(f"'{user_input}' is not a palindrome.")