import React, { useState } from 'react';

interface FormData {
  username: string;
  password: string;
  firstName?: string;
  lastName?: string;
  email?: string;
  phoneNumber?: string;
  licenseNum?: string;
  driverSponsor?: string;
}

interface ValidationErrors {
  username?: string;
  password?: string;
  firstName?: string;
  lastName?: string;
  email?: string;
  phoneNumber?: string;
  licenseNum?: string;
  driverSponsor?: string;
  general?: string;
}

const API_BASE_URL = process.env.APP_API_URL || 'http://localhost:5000';

const LoginPage: React.FC = () => {
  const [isSignUp, setIsSignUp] = useState<boolean>(false);
  const [formData, setFormData] = useState<FormData>({ 
    username: '', 
    password: '',
    firstName: '',
    lastName: '',
    email: '',
    phoneNumber: '',
    licenseNum: '',
    driverSponsor: ''
  });
  const [errors, setErrors] = useState<ValidationErrors>({});
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const validateForm = (): boolean => {
    const newErrors: ValidationErrors = {};

    //Username validation
    if (!formData.username.trim()) {
      newErrors.username = 'Username is required';
    } else if (formData.username.length < 3) {
      newErrors.username = 'Username must be at least 3 characters';
    }

    //Password validation
    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }

    //Additional validation for sign up
    if (isSignUp) {
      if (!formData.firstName?.trim()) {
        newErrors.firstName = 'First name is required';
      }

      if (!formData.lastName?.trim()) {
        newErrors.lastName = 'Last name is required';
      }

      if (!formData.email?.trim()) {
        newErrors.email = 'Email is required';
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
        newErrors.email = 'Invalid email format';
      }

      if (!formData.phoneNumber?.trim()) {
        newErrors.phoneNumber = 'Phone number is required';
      } else if (!/^\d{10}$/.test(formData.phoneNumber.replace(/[-\s()]/g, ''))) {
        newErrors.phoneNumber = 'Phone number must be 10 digits';
      }

      if (!formData.licenseNum?.trim()) {
        newErrors.licenseNum = 'License number is required';
      }

      if (!formData.driverSponsor?.trim()) {
        newErrors.driverSponsor = 'Sponsor is required';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrors({});

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const endpoint = isSignUp ? '/api/auth/signup' : '/api/auth/login';
      
      //Prepare request body based on mode
      const requestBody = isSignUp ? {
        username: formData.username,
        password: formData.password,
        firstName: formData.firstName,
        lastName: formData.lastName,
        email: formData.email,
        phoneNumber: formData.phoneNumber,
        licenseNum: formData.licenseNum,
        driverSponsor: formData.driverSponsor,
        userType: 'driver' //Since this is for drivers
      } : {
        username: formData.username,
        password: formData.password
      };
      
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      const data = await response.json();

      if (!response.ok) {
        setErrors({ 
          general: data.message || data.error || 'Authentication failed. Please try again.' 
        });
        return;
      }

      if (isSignUp) {
        alert('Account created successfully! Please log in.');
        setIsSignUp(false);
        setFormData({ 
          username: '', 
          password: '',
          firstName: '',
          lastName: '',
          email: '',
          phoneNumber: '',
          licenseNum: '',
          driverSponsor: ''
        });
      } else {
        if (data.token) {
          localStorage.setItem('authToken', data.token);
        }
        
        if (data.user) {
          localStorage.setItem('user', JSON.stringify(data.user));
        }

        window.location.href = '/dashboard';
      }
    } catch (error) {
      console.error('API Error:', error);
      setErrors({ 
        general: 'Network error. Please check your connection and try again.' 
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name as keyof ValidationErrors]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const toggleMode = () => {
    setIsSignUp(!isSignUp);
    setFormData({ 
      username: '', 
      password: '',
      firstName: '',
      lastName: '',
      email: '',
      phoneNumber: '',
      licenseNum: '',
      driverSponsor: ''
    });
    setErrors({});
  };

  const renderInput = (
    id: string,
    name: keyof FormData,
    label: string,
    type: string = 'text',
    placeholder: string = ''
  ) => (
    <div style={{ marginBottom: '1rem' }}>
      <label htmlFor={id} style={{
        display: 'block',
        fontSize: '0.875rem',
        fontWeight: '500',
        color: '#374151',
        marginBottom: '0.5rem'
      }}>
        {label}
      </label>
      {errors[name] && (
        <div style={{
          backgroundColor: '#fee2e2',
          color: '#991b1b',
          padding: '0.5rem',
          borderRadius: '4px',
          marginBottom: '0.5rem',
          fontSize: '0.813rem'
        }}>
          {errors[name]}
        </div>
      )}
      <input
        type={type}
        id={id}
        name={name}
        value={formData[name] || ''}
        onChange={handleInputChange}
        disabled={isLoading}
        autoComplete={name === 'password' ? (isSignUp ? 'new-password' : 'current-password') : name}
        style={{
          width: '100%',
          padding: '0.625rem',
          border: `1px solid ${errors[name] ? '#ef4444' : '#d1d5db'}`,
          borderRadius: '4px',
          fontSize: '1rem',
          outline: 'none',
          transition: 'border-color 0.2s',
          backgroundColor: isLoading ? '#f9fafb' : 'white',
          boxSizing: 'border-box'
        }}
        onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
        onBlur={(e) => e.target.style.borderColor = errors[name] ? '#ef4444' : '#d1d5db'}
        placeholder={placeholder}
      />
    </div>
  );

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#f3f4f6',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      padding: '1rem'
    }}>
      <div style={{
        backgroundColor: 'white',
        padding: '2rem',
        borderRadius: '8px',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
        width: '100%',
        maxWidth: '500px',
        maxHeight: '90vh',
        overflowY: 'auto'
      }}>
        <h1 style={{
          fontSize: '1.875rem',
          fontWeight: 'bold',
          textAlign: 'center',
          marginBottom: '1.5rem',
          color: '#1f2937'
        }}>
          {isSignUp ? 'Create Driver Account' : 'Driver Login'}
        </h1>

        {errors.general && (
          <div style={{
            backgroundColor: '#fee2e2',
            border: '1px solid #ef4444',
            color: '#991b1b',
            padding: '0.75rem',
            borderRadius: '4px',
            marginBottom: '1rem',
            fontSize: '0.875rem'
          }}>
            {errors.general}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {renderInput('username', 'username', 'Username', 'text', 'Enter your username')}
          {renderInput('password', 'password', 'Password', 'password', 'Enter your password')}

          {isSignUp && (
            <>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: '1fr 1fr', 
                gap: '1rem',
                marginBottom: '1rem'
              }}>
                <div>
                  <label htmlFor="firstName" style={{
                    display: 'block',
                    fontSize: '0.875rem',
                    fontWeight: '500',
                    color: '#374151',
                    marginBottom: '0.5rem'
                  }}>
                    First Name
                  </label>
                  {errors.firstName && (
                    <div style={{
                      backgroundColor: '#fee2e2',
                      color: '#991b1b',
                      padding: '0.5rem',
                      borderRadius: '4px',
                      marginBottom: '0.5rem',
                      fontSize: '0.813rem'
                    }}>
                      {errors.firstName}
                    </div>
                  )}
                  <input
                    type="text"
                    id="firstName"
                    name="firstName"
                    value={formData.firstName || ''}
                    onChange={handleInputChange}
                    disabled={isLoading}
                    style={{
                      width: '100%',
                      padding: '0.625rem',
                      border: `1px solid ${errors.firstName ? '#ef4444' : '#d1d5db'}`,
                      borderRadius: '4px',
                      fontSize: '1rem',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                    placeholder="First name"
                  />
                </div>

                <div>
                  <label htmlFor="lastName" style={{
                    display: 'block',
                    fontSize: '0.875rem',
                    fontWeight: '500',
                    color: '#374151',
                    marginBottom: '0.5rem'
                  }}>
                    Last Name
                  </label>
                  {errors.lastName && (
                    <div style={{
                      backgroundColor: '#fee2e2',
                      color: '#991b1b',
                      padding: '0.5rem',
                      borderRadius: '4px',
                      marginBottom: '0.5rem',
                      fontSize: '0.813rem'
                    }}>
                      {errors.lastName}
                    </div>
                  )}
                  <input
                    type="text"
                    id="lastName"
                    name="lastName"
                    value={formData.lastName || ''}
                    onChange={handleInputChange}
                    disabled={isLoading}
                    style={{
                      width: '100%',
                      padding: '0.625rem',
                      border: `1px solid ${errors.lastName ? '#ef4444' : '#d1d5db'}`,
                      borderRadius: '4px',
                      fontSize: '1rem',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                    placeholder="Last name"
                  />
                </div>
              </div>

              {renderInput('email', 'email', 'Email', 'email', 'your.email@example.com')}
              {renderInput('phoneNumber', 'phoneNumber', 'Phone Number', 'tel', '(123) 456-7890')}
              {renderInput('licenseNum', 'licenseNum', 'License Number', 'text', 'Enter license number')}
              {renderInput('driverSponsor', 'driverSponsor', 'Sponsor', 'text', 'Enter sponsor name')}
            </>
          )}

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: '100%',
              backgroundColor: isLoading ? '#9ca3af' : '#3b82f6',
              color: 'white',
              padding: '0.75rem',
              borderRadius: '4px',
              border: 'none',
              fontSize: '1rem',
              fontWeight: '500',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              marginTop: '1rem'
            }}
            onMouseEnter={(e) => {
              if (!isLoading) e.currentTarget.style.backgroundColor = '#2563eb';
            }}
            onMouseLeave={(e) => {
              if (!isLoading) e.currentTarget.style.backgroundColor = '#3b82f6';
            }}
          >
            {isLoading ? (
              <>
                <div style={{
                  width: '16px',
                  height: '16px',
                  border: '2px solid #ffffff',
                  borderTopColor: 'transparent',
                  borderRadius: '50%',
                  animation: 'spin 0.8s linear infinite'
                }} />
                Processing...
              </>
            ) : (
              isSignUp ? 'Sign Up' : 'Log In'
            )}
          </button>
        </form>

        <div style={{
          marginTop: '1.5rem',
          textAlign: 'center',
          fontSize: '0.875rem',
          color: '#6b7280'
        }}>
          {isSignUp ? (
            <>
              Already have an account?{' '}
              <button
                onClick={toggleMode}
                disabled={isLoading}
                style={{
                  color: '#3b82f6',
                  background: 'none',
                  border: 'none',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  textDecoration: 'underline',
                  fontSize: '0.875rem',
                  padding: 0
                }}
              >
                Log in here
              </button>
            </>
          ) : (
            <>
              New driver?{' '}
              <button
                onClick={toggleMode}
                disabled={isLoading}
                style={{
                  color: '#3b82f6',
                  background: 'none',
                  border: 'none',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  textDecoration: 'underline',
                  fontSize: '0.875rem',
                  padding: 0
                }}
              >
                Create an account
              </button>
            </>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
};

export default LoginPage;