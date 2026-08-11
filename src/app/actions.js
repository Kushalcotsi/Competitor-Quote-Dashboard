'use server'

import { exec } from 'child_process';
import { revalidatePath } from 'next/cache';
import util from 'util';

const execAsync = util.promisify(exec);

export async function updateAIInsights() {
  try {
    console.log('Triggering AI python script...');
    // cd into the ai-backend directory and run the script
    const { stdout, stderr } = await execAsync('cd ai-backend && python3 generate_key_findings.py');
    console.log('AI script finished executing.');
    
    // Revalidate the home page to instantly fetch the new data from the DB
    revalidatePath('/');
    
    return { success: true };
  } catch (error) {
    console.error('Error running AI script:', error);
    return { success: false, error: error.message };
  }
}
