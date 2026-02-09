INSERT INTO SPONSORS (Sponsor_Name, Sponsor_Email, Sponsor_Phone, Sponsor_Address, Sponsor_PointConversion) VALUES
("Test Sponsor", "abc@123.com", "123-456-7890", "Test Address", 0.01);

INSERT INTO USERS (Username, Encrypted_Password, User_FName, User_LName, User_Email, User_Phone_Num, User_Type) VALUES
("kkvarnl", "Test", "Kyle", "Kvarnlov", "kkvarnl@clemson.edu", "218-452-3376", "Admin"),
("saclayt", "Hello", "Inari", "Clayton", "saclayt@clemson.edu", "123-456-7890", "Admin"),
("dandriy", "World", "David", "Andriychuk", "dandriy@clemson.edu", "234-567-8901", "Admin"),
("csmonta", "Tiger", "Christopher", "Montague", "csmonta@clemson.edu", "345-678-9012", "Admin"),
("driver", "Drives", "Driver", "Driver", "Driver@driver.com", "1-800-Driver", "Driver");

INSERT INTO ADMINS (User_ID) VALUES
(1),
(2),
(3),
(4);

INSERT INTO DRIVERS(User_ID, License_Num, User_Points, Sponsor_ID, App_Status) VALUES
(5, "M87676767", 100, 1, "Received");

INSERT INTO INVENTORY (Prod_SKU, Item_Name, Prod_Description, Prod_Quantity, Prod_UnitPrice) VALUES
("QZY-123", "Test 1", "Test For Subtraction trigger", 35, 12.99);


INSERT INTO ORDERS(Driver_ID, Sponsor_ID, Order_Status, Total_Points) VALUES
(5, 1, "Pending", 25);

INSERT INTO LINE_ITEMS(Item_ID, Order_ID, Prod_SKU, Item_Name, Price_Points, Line_Quantity) VALUES
(1, 1, "QZY-123", "Test 1", 4, 13);


