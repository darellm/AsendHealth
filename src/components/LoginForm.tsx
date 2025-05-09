import React, { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";

const LoginForm = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [userType, setUserType] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    
    setIsLoading(true);
    
    // Simulate API call
    setTimeout(() => {
      setIsLoading(false);
      console.log("Login attempt with:", { userType, username, password });
      // In a real app, this would be where you handle authentication
    }, 1500);
  };

  return (
    <Card className="w-full max-w-md animate-fade-in shadow-lg bg-white/80 backdrop-blur-md">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl text-center font-bold">Welcome Back</CardTitle>
        <CardDescription className="text-center">
          Please log in to access your services
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleLogin} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="userType">User Type</Label>
            <Select value={userType} onValueChange={setUserType}>
              <SelectTrigger id="userType" className="form-input">
                <SelectValue placeholder="Select User Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="patient">Patient</SelectItem>
                  <SelectItem value="doctor">Doctor</SelectItem>
                  <SelectItem value="admin">Administrator</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          
          <div className="space-y-2 animate-slide-up" style={{ animationDelay: '0.1s' }}>
            <Label htmlFor="username">Username</Label>
            <Input 
              id="username" 
              type="text" 
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="form-input"
              required
            />
          </div>
          
          <div className="space-y-2 animate-slide-up" style={{ animationDelay: '0.2s' }}>
            <div className="flex justify-between">
              <Label htmlFor="password">Password</Label>
              <a 
                href="#" 
                className="text-sm font-medium text-primary hover:underline"
              >
                Forgot password?
              </a>
            </div>
            <Input 
              id="password" 
              type="password" 
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="form-input"
              required
            />
          </div>
          
          <div className="animate-slide-up" style={{ animationDelay: '0.3s' }}>
            <Button 
              type="submit" 
              className="auth-button"
              disabled={isLoading}
            >
              {isLoading ? (
                <div className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Logging in...
                </div>
              ) : (
                <span>Login</span>
              )}
            </Button>
          </div>
        </form>
      </CardContent>
      <CardFooter className="flex flex-col space-y-2 text-center text-sm">
        <a href="#" className="text-primary hover:underline">
          Trouble logging in?
        </a>
        <div>
          Don't have an account? {" "}
          <a href="#" className="font-medium text-primary hover:underline">
            Sign up now
          </a>
        </div>
      </CardFooter>
    </Card>
  );
};

export default LoginForm;