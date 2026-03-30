DELIMITER $$

CREATE TRIGGER Inventory_Check
BEFORE INSERT ON LINE_ITEMS FOR EACH ROW
BEGIN
	IF (SELECT Prod_Quantity FROM INVENTORY WHERE Item_ID = NEW.Item_ID) < NEW.Line_Quantity THEN
		SIGNAL SQLSTATE "45000"
			SET MESSAGE_TEXT = "Inventory too low for this order.";
	END IF;
END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER Inventory_Delete
AFTER INSERT ON LINE_ITEMS FOR EACH ROW
BEGIN
	UPDATE INVENTORY
    SET Prod_Quantity = Prod_Quantity - NEW.Line_Quantity WHERE Item_ID = New.Item_ID;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER Application_Approved
AFTER UPDATE ON APPLICATIONS FOR EACH ROW
BEGIN
	IF NEW.App_Status = 'Approved' AND OLD.App_Status <> 'Approved' THEN
		INSERT INTO USERS(Username, Encrypted_Password, User_FName, User_LNAME, User_Email, User_Phone_Num, User_Type) VALUES
        (NEW.App_Username, NEW.Encrypted_Password, NEW.App_FName, NEW.App_LNAME, NEW.App_Email, NEW.App_Phone_Num, 'Driver');
        SET @new_uid = LAST_INSERT_ID();
        INSERT INTO DRIVERS (User_ID, License_Num, Is_Active) VALUES
        (@new_uid, NEW.License_Num, TRUE);
		INSERT INTO DRIVER_SPONSORS (Driver_ID, Sponsor_ID, Created_At, Is_Active, Driver_Points) VALUES
        (@new_uid, NEW.App_Sponsor_ID, CURRENT_TIMESTAMP, TRUE, 0);
	END IF;
END$$

DELIMITER ;

DELIMITER $$

CREATE TRIGGER Check_Point_Balance
BEFORE INSERT ON ORDERS FOR EACH ROW
BEGIN
	DECLARE Point_Balance INT;
    
	SELECT User_Points INTO Point_Balance FROM DRIVERS WHERE User_ID = NEW.Driver_ID;
    
    IF NEW.Total_Points > Point_Balance THEN SIGNAL SQLSTATE '45000'
		SET MESSAGE_TEXT = "Insufficient Balance";
	END IF;
END$$

DELIMITER ;
	
DELIMITER $$

CREATE TRIGGER Multi_Application_Approved
AFTER UPDATE ON DRIVER_SPONSOR_APPLICATIONS FOR EACH ROW
BEGIN
	IF NEW.Application_Status = 'Approved' AND OLD.Application_Status <> 'Approved' THEN
		INSERT INTO DRIVER_SPONSORS(Driver_ID, Sponsor_ID, Is_Active, Driver_Points) VALUES
       (NEW.Driver_ID, NEW.App_Sponsor_ID, TRUE, 0);
	END IF;
END$$

DELIMITER ;